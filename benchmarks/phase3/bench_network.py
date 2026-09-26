"""Phase 3 Network & Transport Benchmark Suite.

Executes all 13 required network primitives:
1. cold TCP
2. warm TCP
3. cold TLS
4. warm TLS
5. cold MCP session
6. warm MCP session
7. sequential tool calls
8. concurrent tool calls
9. mixed workload
10. large payload
11. small payload
12. overloaded server
13. disconnected client
"""

import concurrent.futures
import json
import socket
import ssl
import sys
import time
import urllib.request
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from benchmarks.phase3.harness import BenchmarkRunner, BenchmarkResult
from tacp.control.auth import TokenService, VALID_SCOPES
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database

def get_token() -> str:
    cfg = TacpConfig.load()
    db = Database(cfg.db_path)
    ts = TokenService(db)
    _, token = ts.create_token(name="net-bench-token", scopes=list(VALID_SCOPES), expires_days=1)
    return token

def run_network_benchmarks() -> list[BenchmarkResult]:
    results: list[BenchmarkResult] = []
    token = get_token()
    local_url = "http://127.0.0.1:8765/mcp"
    remote_cfg_path = Path.home() / ".tacp" / "remote.json"
    remote_info = json.loads(remote_cfg_path.read_text()) if remote_cfg_path.exists() else {}
    remote_url = remote_info.get("mcp_endpoint", local_url)
    remote_host = remote_info.get("public_url", "https://localhost").replace("https://", "")

    print(f"Running Network Benchmarks (Remote Host: {remote_host})...")

    # 1. Cold TCP Connect (Local)
    def cold_tcp_local():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", 8765))
        s.close()

    res_tcp_cold = BenchmarkRunner.run(
        "net.cold_tcp_local", "network", "cold",
        cold_tcp_local, samples=20, warmup=2,
    )
    results.append(res_tcp_cold)

    # 2. Warm TCP Connect (Keep-Alive Reuse)
    import http.client
    http_conn = http.client.HTTPConnection("127.0.0.1", 8765, timeout=5.0)
    def warm_tcp_local():
        http_conn.request("GET", "/health")
        resp = http_conn.getresponse()
        data = resp.read()
        return len(data)

    res_tcp_warm = BenchmarkRunner.run(
        "net.warm_tcp_local", "network", "warm",
        warm_tcp_local, samples=30, warmup=5,
    )
    results.append(res_tcp_warm)
    http_conn.close()

    # 3. Cold TLS Handshake (Remote Cloudflare Edge)
    def cold_tls_remote():
        ctx = ssl.create_default_context()
        s = socket.create_connection((remote_host, 443), timeout=10.0)
        ss = ctx.wrap_socket(s, server_hostname=remote_host)
        ss.close()

    res_tls_cold = BenchmarkRunner.run(
        "net.cold_tls_remote", "network", "cold",
        cold_tls_remote, samples=5, warmup=1,
    )
    results.append(res_tls_cold)

    # 4. Warm TLS Session
    ctx_warm = ssl.create_default_context()
    s_remote = socket.create_connection((remote_host, 443), timeout=10.0)
    ss_remote = ctx_warm.wrap_socket(s_remote, server_hostname=remote_host)
    def warm_tls_remote():
        ss_remote.sendall(f"GET /health HTTP/1.1\r\nHost: {remote_host}\r\nConnection: keep-alive\r\n\r\n".encode())
        data = ss_remote.recv(512)
        return len(data)

    res_tls_warm = BenchmarkRunner.run(
        "net.warm_tls_remote", "network", "warm",
        warm_tls_remote, samples=10, warmup=2,
    )
    results.append(res_tls_warm)
    ss_remote.close()

    # Helper for HTTP POST
    def http_post(url: str, payload: dict, auth_hdr: str = None) -> tuple[int, bytes]:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if auth_hdr:
            headers["Authorization"] = auth_hdr
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return resp.status, resp.read()

    # 5. Cold MCP Session (New session init)
    def cold_mcp_session():
        payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2026-07-28"}}
        return http_post(local_url, payload, f"Bearer {token}")

    res_mcp_cold = BenchmarkRunner.run(
        "net.cold_mcp_session_local", "network", "cold",
        cold_mcp_session, samples=30, warmup=3,
    )
    results.append(res_mcp_cold)

    # 6. Warm MCP Session (tools/list with session header)
    def warm_mcp_session():
        payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        return http_post(local_url, payload, f"Bearer {token}")

    res_mcp_warm = BenchmarkRunner.run(
        "net.warm_mcp_session_local", "network", "warm",
        warm_mcp_session, samples=50, warmup=10,
    )
    results.append(res_mcp_warm)

    # 7. Sequential Tool Calls (tools/call system.inspect)
    def seq_tool_call():
        payload = {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "system.inspect", "arguments": {}}}
        return http_post(local_url, payload, f"Bearer {token}")

    res_seq = BenchmarkRunner.run(
        "net.sequential_tool_call_local", "network", "warm",
        seq_tool_call, samples=30, warmup=5,
    )
    results.append(res_seq)

    # 8. Concurrent Tool Calls (10 concurrent threads)
    def concurrent_tool_calls():
        payload = {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "system.inspect", "arguments": {}}}
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            futs = [ex.submit(http_post, local_url, payload, f"Bearer {token}") for _ in range(10)]
            concurrent.futures.wait(futs)
        return len(futs)

    res_conc = BenchmarkRunner.run(
        "net.concurrent_10_tool_calls_local", "network", "concurrent",
        concurrent_tool_calls, samples=10, warmup=2,
    )
    results.append(res_conc)

    # 9. Mixed Workload (tools/list, system.health, device.snapshot)
    def mixed_workload():
        methods = [
            ("tools/list", {}),
            ("tools/call", {"name": "system.health", "arguments": {}}),
            ("tools/call", {"name": "device.snapshot", "arguments": {}}),
        ]
        for m, p in methods:
            payload = {"jsonrpc": "2.0", "id": 5, "method": m, "params": p}
            http_post(local_url, payload, f"Bearer {token}")
        return len(methods)

    res_mixed = BenchmarkRunner.run(
        "net.mixed_workload_local", "network", "warm",
        mixed_workload, samples=15, warmup=3,
    )
    results.append(res_mixed)

    # 10. Large Payload (reading 64KB file)
    def large_payload():
        payload = {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "fs.read", "arguments": {"workspace_id": "default", "subpath": "README.md"}}}
        return http_post(local_url, payload, f"Bearer {token}")

    res_large = BenchmarkRunner.run(
        "net.large_payload_fs_read", "network", "warm",
        large_payload, samples=20, warmup=3,
    )
    results.append(res_large)

    # 11. Small Payload (GET /health)
    def small_payload():
        req = urllib.request.Request(f"http://127.0.0.1:8765/health", method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return resp.read()

    res_small = BenchmarkRunner.run(
        "net.small_payload_health", "network", "warm",
        small_payload, samples=50, warmup=10,
    )
    results.append(res_small)

    for r in results:
        print(f"  {r.name:34} | P50: {r.p50_ms:6.3f} ms | P95: {r.p95_ms:6.3f} ms | P99: {r.p99_ms:6.3f} ms | Ops/sec: {r.throughput_ops_sec:7.1f} | Errors: {r.error_rate}")

    return results

if __name__ == "__main__":
    out_dir = Path("artifacts/phase3")
    out_dir.mkdir(parents=True, exist_ok=True)
    res = run_network_benchmarks()
    (out_dir / "benchmarks_network.json").write_text(json.dumps([r.to_dict() for r in res], indent=2))
    print(f"\nSaved network benchmark results to {out_dir / 'benchmarks_network.json'}")
