import argparse
import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

from cache_comparison.load_generator import run_load


def _http_get_json(url: str, path: str) -> Dict[str, Any]:
    import json as _json
    from http.client import HTTPConnection

    u = urlparse(url)
    conn = HTTPConnection(u.hostname, u.port, timeout=5)
    conn.request("GET", path, headers={"Connection": "close"})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    if resp.status != 200:
        raise RuntimeError(f"GET {path} failed: {resp.status}")
    return _json.loads(data.decode("utf-8"))


def _wait_healthy(base_url: str, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + float(timeout_s)
    last_err = None
    while time.monotonic() < deadline:
        try:
            _http_get_json(base_url, "/health")
            return
        except Exception as e:
            last_err = e
            time.sleep(0.1)
    raise RuntimeError(f"Server not healthy: {last_err}")


def _shutdown(base_url: str) -> None:
    try:
        _http_get_json(base_url, "/shutdown")
    except Exception:
        return None


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _print_table(rows: List[Dict[str, Any]]) -> None:
    headers = [
        "strategy",
        "profile",
        "throughput_rps",
        "avg_latency_ms",
        "db_reads",
        "db_writes",
        "cache_hit_rate",
        "wb_max_pending",
    ]
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join(["---"] * len(headers)) + "|")
    for r in rows:
        print(
            "| "
            + " | ".join(
                [
                    str(r.get("strategy")),
                    str(r.get("profile")),
                    f'{r.get("throughput_rps"):.2f}',
                    f'{r.get("avg_latency_ms"):.2f}',
                    str(r.get("db_reads")),
                    str(r.get("db_writes")),
                    f'{r.get("cache_hit_rate"):.3f}',
                    str(r.get("wb_max_pending")),
                ]
            )
            + " |"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--keys", type=int, default=2000)
    parser.add_argument("--workers", type=int, default=80)
    parser.add_argument("--duration-s", type=float, default=10.0)
    parser.add_argument("--db-delay-ms", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out-json", default="")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{int(args.port)}"
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    data_dir = os.path.abspath(data_dir)
    _ensure_dir(data_dir)

    strategies = ["cache_aside", "write_through", "write_back"]
    profiles = [
        ("read-heavy", 80, 20),
        ("balanced", 50, 50),
        ("write-heavy", 20, 80),
    ]

    all_rows: List[Dict[str, Any]] = []
    raw: Dict[str, Any] = {"base_url": base_url, "strategies": {}}

    for strategy in strategies:
        db_path = os.path.join(data_dir, f"{strategy}.sqlite")
        if os.path.exists(db_path):
            os.remove(db_path)

        seed_cmd = [sys.executable, "-m", "cache_comparison.seed_db", "--db-path", db_path, "--keys", str(args.keys), "--seed", str(args.seed)]
        subprocess.check_call(seed_cmd, cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

        server_cmd = [
            sys.executable,
            "-m",
            "cache_comparison.server",
            "--host",
            str(args.host),
            "--port",
            str(args.port),
            "--db-path",
            db_path,
            "--strategy",
            strategy,
            "--db-delay-ms",
            str(args.db_delay_ms),
            "--allow-shutdown",
        ]
        proc = subprocess.Popen(server_cmd, cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        try:
            _wait_healthy(base_url, timeout_s=10.0)
            raw["strategies"][strategy] = {}

            poll_wb = strategy == "write_back"
            for profile_name, read_pct, write_pct in profiles:
                res = run_load(
                    base_url=base_url,
                    keys=int(args.keys),
                    workers=int(args.workers),
                    duration_s=float(args.duration_s),
                    read_pct=int(read_pct),
                    write_pct=int(write_pct),
                    seed=int(args.seed),
                    poll_writeback=poll_wb and profile_name == "write-heavy",
                )
                d = res.server_delta
                row = {
                    "strategy": strategy,
                    "profile": profile_name,
                    "throughput_rps": res.throughput_rps,
                    "avg_latency_ms": res.avg_latency_ms,
                    "db_reads": d["db"]["reads"],
                    "db_writes": d["db"]["writes"],
                    "cache_hit_rate": d["cache"]["hit_rate"],
                    "wb_max_pending": (d["write_back"]["max_pending_keys"] if d.get("write_back") else None),
                }
                all_rows.append(row)
                raw["strategies"][strategy][profile_name] = {
                    "load": {
                        "workers": res.workers,
                        "duration_s": res.duration_s,
                        "read_pct": res.read_pct,
                        "write_pct": res.write_pct,
                        "keys": res.keys,
                    },
                    "client": {
                        "requests": res.requests,
                        "errors": res.errors,
                        "throughput_rps": res.throughput_rps,
                        "avg_latency_ms": res.avg_latency_ms,
                    },
                    "server_delta": res.server_delta,
                }

            if strategy == "write_back":
                deadline = time.monotonic() + 10.0
                while time.monotonic() < deadline:
                    m = _http_get_json(base_url, "/metrics")
                    pending = (m.get("write_back") or {}).get("pending_keys")
                    if pending in (None, 0):
                        break
                    time.sleep(0.2)
        finally:
            _shutdown(base_url)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    try:
                        proc.wait(timeout=3)
                    except Exception:
                        pass

    _print_table(all_rows)

    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
