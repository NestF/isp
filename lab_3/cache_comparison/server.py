import argparse
import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from cache_comparison.cache import InMemoryCache
from cache_comparison.db import SqliteDb
from cache_comparison.strategies import (
    CacheAsideWriteAroundStrategy,
    StorageStrategy,
    WriteBackStrategy,
    WriteThroughStrategy,
)


class AppContext:
    def __init__(self, strategy: StorageStrategy, allow_shutdown: bool) -> None:
        self.strategy = strategy
        self.allow_shutdown = allow_shutdown
        self.started_at = time.time()


CTX: Optional[AppContext] = None


def _read_json(handler: BaseHTTPRequestHandler) -> Any:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    body = handler.rfile.read(length) if length > 0 else b""
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _write_json(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    server: ThreadingHTTPServer

    def log_message(self, format: str, *args: object) -> None:
        return None

    def do_GET(self) -> None:
        ctx = CTX
        if ctx is None:
            _write_json(self, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "not_ready"})
            return

        parsed = urlparse(self.path)
        if parsed.path == "/health":
            _write_json(self, HTTPStatus.OK, {"status": "ok"})
            return

        if parsed.path == "/metrics":
            m = ctx.strategy.metrics()
            _write_json(
                self,
                HTTPStatus.OK,
                {
                    "strategy": m.strategy,
                    "started_at": ctx.started_at,
                    "cache": {
                        "hits": m.cache_hits,
                        "misses": m.cache_misses,
                        "hit_rate": m.cache_hit_rate,
                        "size": m.cache_size,
                    },
                    "db": {"reads": m.db_reads, "writes": m.db_writes},
                    "write_back": {
                        "pending_keys": m.writeback_pending_keys,
                        "max_pending_keys": m.writeback_max_pending_keys,
                        "enqueued_writes": m.writeback_enqueued_writes,
                        "flushed_writes": m.writeback_flushed_writes,
                        "flush_errors": m.writeback_flush_errors,
                        "last_flush_ts": m.writeback_last_flush_ts,
                    },
                },
            )
            return

        if parsed.path == "/shutdown":
            if not ctx.allow_shutdown:
                _write_json(self, HTTPStatus.FORBIDDEN, {"error": "shutdown_disabled"})
                return

            _write_json(self, HTTPStatus.OK, {"status": "shutting_down"})

            def _shutdown() -> None:
                try:
                    self.server.shutdown()
                except Exception:
                    return None

            threading.Thread(target=_shutdown, daemon=True).start()
            return

        if parsed.path.startswith("/items/"):
            item_id = parsed.path[len("/items/") :]
            if not item_id:
                _write_json(self, HTTPStatus.BAD_REQUEST, {"error": "missing_id"})
                return
            value = ctx.strategy.get(item_id)
            if value is None:
                _write_json(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            _write_json(self, HTTPStatus.OK, {"id": item_id, "value": value})
            return

        _write_json(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_PUT(self) -> None:
        ctx = CTX
        if ctx is None:
            _write_json(self, HTTPStatus.SERVICE_UNAVAILABLE, {"error": "not_ready"})
            return

        parsed = urlparse(self.path)
        if not parsed.path.startswith("/items/"):
            _write_json(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return

        item_id = parsed.path[len("/items/") :]
        if not item_id:
            _write_json(self, HTTPStatus.BAD_REQUEST, {"error": "missing_id"})
            return

        try:
            payload = _read_json(self)
        except Exception:
            _write_json(self, HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return

        if not isinstance(payload, dict) or "value" not in payload:
            _write_json(self, HTTPStatus.BAD_REQUEST, {"error": "expected_{value:...}"})
            return

        ctx.strategy.set(item_id, payload["value"])
        _write_json(self, HTTPStatus.OK, {"status": "ok"})


def build_strategy(
    strategy_name: str,
    db: SqliteDb,
    cache_ttl_seconds: Optional[float],
    writeback_flush_interval_ms: int,
    writeback_max_batch: int,
) -> StorageStrategy:
    cache = InMemoryCache(ttl_seconds=cache_ttl_seconds)
    if strategy_name == "cache_aside":
        return CacheAsideWriteAroundStrategy(db=db, cache=cache)
    if strategy_name == "write_through":
        return WriteThroughStrategy(db=db, cache=cache)
    if strategy_name == "write_back":
        return WriteBackStrategy(
            db=db,
            cache=cache,
            flush_interval_ms=writeback_flush_interval_ms,
            max_batch=writeback_max_batch,
        )
    raise ValueError(f"Unknown strategy: {strategy_name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--strategy", choices=["cache_aside", "write_through", "write_back"], required=True)
    parser.add_argument("--db-delay-ms", type=float, default=5.0)
    parser.add_argument("--cache-ttl-sec", type=float, default=0.0)
    parser.add_argument("--writeback-flush-interval-ms", type=int, default=200)
    parser.add_argument("--writeback-max-batch", type=int, default=200)
    parser.add_argument("--allow-shutdown", action="store_true")
    args = parser.parse_args()

    cache_ttl_seconds = None if args.cache_ttl_sec <= 0 else float(args.cache_ttl_sec)
    db = SqliteDb(db_path=args.db_path, artificial_delay_ms=args.db_delay_ms)
    strategy = build_strategy(
        strategy_name=args.strategy,
        db=db,
        cache_ttl_seconds=cache_ttl_seconds,
        writeback_flush_interval_ms=args.writeback_flush_interval_ms,
        writeback_max_batch=args.writeback_max_batch,
    )

    global CTX
    CTX = AppContext(strategy=strategy, allow_shutdown=bool(args.allow_shutdown))

    server = ThreadingHTTPServer((args.host, int(args.port)), Handler)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        try:
            strategy.close()
        finally:
            db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

