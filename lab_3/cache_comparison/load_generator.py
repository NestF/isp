import argparse
import json
import random
import statistics
import threading
import time
from dataclasses import dataclass
from http.client import HTTPConnection
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse


@dataclass(frozen=True)
class LoadResult:
    base_url: str
    duration_s: float
    workers: int
    keys: int
    read_pct: int
    write_pct: int
    requests: int
    errors: int
    throughput_rps: float
    avg_latency_ms: float
    server_delta: Dict[str, Any]


def _http_json(method: str, base_url: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[int, Any]:
    u = urlparse(base_url)
    conn = HTTPConnection(u.hostname, u.port, timeout=10)
    headers = {"Connection": "close"}
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
        headers["Content-Length"] = str(len(body))
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    parsed = None
    if data:
        parsed = json.loads(data.decode("utf-8"))
    return resp.status, parsed


def _get_metrics(base_url: str) -> Dict[str, Any]:
    status, data = _http_json("GET", base_url, "/metrics")
    if status != 200 or not isinstance(data, dict):
        raise RuntimeError(f"Failed to fetch /metrics: status={status}, data={data}")
    return data


def _delta_metrics(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    b_cache = before.get("cache") or {}
    a_cache = after.get("cache") or {}
    b_db = before.get("db") or {}
    a_db = after.get("db") or {}
    b_wb = before.get("write_back") or {}
    a_wb = after.get("write_back") or {}

    cache_hits = int(a_cache.get("hits") or 0) - int(b_cache.get("hits") or 0)
    cache_misses = int(a_cache.get("misses") or 0) - int(b_cache.get("misses") or 0)
    denom = cache_hits + cache_misses
    hit_rate = (cache_hits / denom) if denom > 0 else 0.0

    return {
        "strategy": after.get("strategy"),
        "cache": {
            "hits": cache_hits,
            "misses": cache_misses,
            "hit_rate": hit_rate,
        },
        "db": {
            "reads": int(a_db.get("reads") or 0) - int(b_db.get("reads") or 0),
            "writes": int(a_db.get("writes") or 0) - int(b_db.get("writes") or 0),
        },
        "write_back": {
            "pending_keys_end": a_wb.get("pending_keys"),
            "max_pending_keys": a_wb.get("max_pending_keys"),
            "enqueued_writes": (None if a_wb.get("enqueued_writes") is None else int(a_wb.get("enqueued_writes") or 0) - int(b_wb.get("enqueued_writes") or 0)),
            "flushed_writes": (None if a_wb.get("flushed_writes") is None else int(a_wb.get("flushed_writes") or 0) - int(b_wb.get("flushed_writes") or 0)),
            "flush_errors": a_wb.get("flush_errors"),
        },
    }


def run_load(
    base_url: str,
    keys: int,
    workers: int,
    duration_s: float,
    read_pct: int,
    write_pct: int,
    seed: int,
    poll_writeback: bool = False,
) -> LoadResult:
    if read_pct + write_pct != 100:
        raise ValueError("read_pct + write_pct must be 100")

    before = _get_metrics(base_url)

    start = time.monotonic()
    end_at = start + float(duration_s)
    errors = 0
    req_count = 0
    latency_sum_s = 0.0
    latency_samples_ms = []
    lock = threading.Lock()

    u = urlparse(base_url)

    stop_poll = threading.Event()

    def poller() -> None:
        while not stop_poll.is_set():
            stop_poll.wait(1.0)
            if stop_poll.is_set():
                break
            try:
                m = _get_metrics(base_url)
                wb = m.get("write_back") or {}
                pending = wb.get("pending_keys")
                if pending is not None:
                    print(f"write_back.pending_keys={pending}")
            except Exception:
                continue

    poll_thread = None
    if poll_writeback:
        poll_thread = threading.Thread(target=poller, daemon=True)
        poll_thread.start()

    def worker(worker_id: int) -> None:
        nonlocal errors, req_count, latency_sum_s
        rnd = random.Random(int(seed) + worker_id * 100_000)
        conn = HTTPConnection(u.hostname, u.port, timeout=10)
        while time.monotonic() < end_at:
            op_roll = rnd.randint(1, 100)
            item_id = f"item-{rnd.randrange(0, keys)}"
            t0 = time.monotonic()
            try:
                if op_roll <= read_pct:
                    conn.request("GET", f"/items/{item_id}", headers={"Connection": "keep-alive"})
                    resp = conn.getresponse()
                    resp.read()
                    ok = resp.status == 200
                else:
                    value = {"n": rnd.randint(0, 1_000_000), "v": f"w-{worker_id}-{rnd.randint(0, 1_000_000)}"}
                    body = json.dumps({"value": value}, ensure_ascii=False).encode("utf-8")
                    headers = {
                        "Connection": "keep-alive",
                        "Content-Type": "application/json; charset=utf-8",
                        "Content-Length": str(len(body)),
                    }
                    conn.request("PUT", f"/items/{item_id}", body=body, headers=headers)
                    resp = conn.getresponse()
                    resp.read()
                    ok = resp.status == 200
            except Exception:
                ok = False
            t1 = time.monotonic()
            dt = t1 - t0

            with lock:
                req_count += 1
                latency_sum_s += dt
                if len(latency_samples_ms) < 5000:
                    latency_samples_ms.append(dt * 1000.0)
                if not ok:
                    errors += 1
        try:
            conn.close()
        except Exception:
            return None

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(int(workers))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    stop_poll.set()
    if poll_thread is not None:
        poll_thread.join(timeout=1.0)

    after = _get_metrics(base_url)
    wall = time.monotonic() - start
    throughput = (req_count / wall) if wall > 0 else 0.0
    avg_latency_ms = (latency_sum_s / req_count) * 1000.0 if req_count > 0 else 0.0

    if latency_samples_ms:
        try:
            p95 = statistics.quantiles(latency_samples_ms, n=20)[18]
        except Exception:
            p95 = None
    else:
        p95 = None

    delta = _delta_metrics(before, after)
    if p95 is not None:
        delta["client_p95_latency_ms_sampled"] = float(p95)

    return LoadResult(
        base_url=base_url,
        duration_s=float(wall),
        workers=int(workers),
        keys=int(keys),
        read_pct=int(read_pct),
        write_pct=int(write_pct),
        requests=int(req_count),
        errors=int(errors),
        throughput_rps=float(throughput),
        avg_latency_ms=float(avg_latency_ms),
        server_delta=delta,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--keys", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--duration-s", type=float, default=10.0)
    parser.add_argument("--read-pct", type=int, default=80)
    parser.add_argument("--write-pct", type=int, default=20)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--poll-writeback", action="store_true")
    args = parser.parse_args()

    res = run_load(
        base_url=args.base_url,
        keys=int(args.keys),
        workers=int(args.workers),
        duration_s=float(args.duration_s),
        read_pct=int(args.read_pct),
        write_pct=int(args.write_pct),
        seed=int(args.seed),
        poll_writeback=bool(args.poll_writeback),
    )

    print(
        json.dumps(
            {
                "throughput_rps": res.throughput_rps,
                "avg_latency_ms": res.avg_latency_ms,
                "requests": res.requests,
                "errors": res.errors,
                "server_delta": res.server_delta,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

