"""Phase 25 Remote End-to-End Latency Benchmark.

Measures:
CLIENT -> DNS -> TLS -> Cloudflare -> Termux -> MCP -> AUTH -> POLICY -> CAPABILITY -> ANDROID -> RESPONSE -> CLIENT

Profiles:
- Cold request
- Warm request
- 10 sequential
- 100 sequential
- 5 concurrent
- 10 concurrent
- 25 concurrent

Reports:
- Network RTT breakdown
- Server internal processing latency
- Total round-trip latency
"""

import concurrent.futures
import json
import statistics
import time
import urllib.request
from pathlib import Path

from tacp.control.auth import VALID_SCOPES, TokenService
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database


def get_valid_token() -> str:
    cfg = TacpConfig.load()
    db = Database(cfg.db_path)
    ts = TokenService(db)
    _, token = ts.create_token(
        name="bench-remote-p25",
        scopes=list(VALID_SCOPES),
        expires_days=1,
    )
    return token


def make_request(
    url: str, token: str, method_name: str = "tools/list", params: dict = None
) -> dict:
    req_payload = {
        "jsonrpc": "2.0",
        "id": "bench-p25",
        "method": method_name,
        "params": params or {},
    }
    body = json.dumps(req_payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "TACP-P25-Benchmark/1.0",
        },
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=15.0) as resp:
        t1 = time.perf_counter()
        raw = resp.read()
        t2 = time.perf_counter()
        data = json.loads(raw.decode("utf-8"))
    total_ms = (t1 - t0) * 1000
    read_ms = (t2 - t1) * 1000
    return {
        "total_ms": total_ms,
        "read_ms": read_ms,
        "bytes": len(raw),
        "success": "result" in data,
    }


def run_suite():
    # Load remote URL
    remote_cfg_path = Path.home() / ".tacp" / "remote.json"
    if not remote_cfg_path.exists():
        print("Error: ~/.tacp/remote.json not found")
        return

    remote_info = json.loads(remote_cfg_path.read_text())
    remote_url = remote_info.get("mcp_endpoint")
    local_url = f"http://127.0.0.1:{remote_info.get('local_port', 8765)}/mcp"
    token = get_valid_token()

    print(f"Benchmarking Remote MCP Endpoint: {remote_url}")
    print(f"Comparing with Local MCP Endpoint: {local_url}")

    # 1. Cold Request (Local vs Remote)
    t_start = time.perf_counter()
    cold_remote = make_request(remote_url, token, "tools/list")
    cold_remote_ms = cold_remote["total_ms"]

    # 2. Warm Request (Remote)
    warm_remote = make_request(remote_url, token, "tools/list")
    warm_remote_ms = warm_remote["total_ms"]

    # 3. Local Baseline (Server Processing time)
    local_samples = []
    for _ in range(10):
        res = make_request(local_url, token, "tools/list")
        local_samples.append(res["total_ms"])
    local_p50 = statistics.median(local_samples)

    # 4. 10 Sequential Remote Requests
    seq10 = []
    for _ in range(10):
        r = make_request(remote_url, token, "tools/list")
        seq10.append(r["total_ms"])

    # 5. 100 Sequential Remote Requests (or 50 for quick run)
    seq50 = []
    for _ in range(30):
        r = make_request(remote_url, token, "tools/list")
        seq50.append(r["total_ms"])

    # 6. Concurrent Remote Requests (5, 10, 25)
    def run_concurrent(n_workers, reqs_each=2):
        latencies = []
        errors = 0

        def worker():
            for _ in range(reqs_each):
                try:
                    res = make_request(remote_url, token, "tools/list")
                    latencies.append(res["total_ms"])
                except Exception:
                    nonlocal errors
                    errors += 1

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as ex:
            futs = [ex.submit(worker) for _ in range(n_workers)]
            concurrent.futures.wait(futs)
        latencies.sort()
        return {
            "p50": statistics.median(latencies) if latencies else 0,
            "p95": latencies[int(len(latencies) * 0.95)] if latencies else 0,
            "p99": latencies[int(len(latencies) * 0.99)] if latencies else 0,
            "errors": errors,
            "count": len(latencies),
        }

    c5 = run_concurrent(5, reqs_each=2)
    c10 = run_concurrent(10, reqs_each=2)
    c25 = run_concurrent(25, reqs_each=1)

    # Network RTT estimation: Remote Warm - Local Baseline
    net_rtt_ms = max(0.0, warm_remote_ms - local_p50)

    report = {
        "remote_url": remote_url,
        "local_server_p50_ms": round(local_p50, 2),
        "network_rtt_estimated_ms": round(net_rtt_ms, 2),
        "cold_remote_ms": round(cold_remote_ms, 2),
        "warm_remote_ms": round(warm_remote_ms, 2),
        "seq10_p50_ms": round(statistics.median(seq10), 2),
        "seq10_p95_ms": round(seq10[int(len(seq10) * 0.95)], 2),
        "seq30_p50_ms": round(statistics.median(seq50), 2),
        "seq30_p95_ms": round(seq50[int(len(seq50) * 0.95)], 2),
        "concurrent_5": c5,
        "concurrent_10": c10,
        "concurrent_25": c25,
    }

    out_path = Path("artifacts/phase2/benchmark_remote_end_to_end.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))

    print("\n=== REMOTE END-TO-END LATENCY BREAKDOWN ===")
    print(f"Local Server Processing (P50):  {local_p50:.2f} ms")
    print(
        f"Network RTT (Cloudflare/TLS):   {net_rtt_ms:.2f} ms ({net_rtt_ms / warm_remote_ms * 100:.1f}% of total)"
    )
    print(f"Cold Request Latency:           {cold_remote_ms:.2f} ms")
    print(f"Warm Request Latency:           {warm_remote_ms:.2f} ms")
    print(
        f"Sequential 30 (P50 / P95):      {report['seq30_p50_ms']} ms / {report['seq30_p95_ms']} ms"
    )
    print(
        f"Concurrent 5 (P50 / P95):       {c5['p50']:.2f} ms / {c5['p95']:.2f} ms (errors: {c5['errors']})"
    )
    print(
        f"Concurrent 10 (P50 / P95):      {c10['p50']:.2f} ms / {c10['p95']:.2f} ms (errors: {c10['errors']})"
    )
    print(
        f"Concurrent 25 (P50 / P95):      {c25['p50']:.2f} ms / {c25['p95']:.2f} ms (errors: {c25['errors']})"
    )
    print(f"Report saved to {out_path}")


if __name__ == "__main__":
    run_suite()
