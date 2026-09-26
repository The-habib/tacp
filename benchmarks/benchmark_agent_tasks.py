"""Phase 26 Agent Task Benchmark Suite.

Benchmarks the 6 core real-world AI agent tasks:
- TASK A: "Give me phone model, Android version, battery, storage and network"
  (Aggregated via device.snapshot vs unoptimized discrete calls)
- TASK B: "List my Downloads folder" (fs.list)
- TASK C: "Find the most recently modified files" (fs.search)
- TASK D: "Show current Termux processes" (process.list)
- TASK E: "Take a screenshot" (screen.capture)
- TASK F: "Check whether the companion is available" (system.health)

Measures:
- Number of MCP calls
- Total latency (Local vs Remote P50/P95)
- Payload size in bytes
- Error rate
"""

import json
import statistics
import time
import urllib.request
from pathlib import Path
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database
from tacp.control.auth import TokenService, VALID_SCOPES

def get_token() -> str:
    cfg = TacpConfig.load()
    db = Database(cfg.db_path)
    ts = TokenService(db)
    _, token = ts.create_token(
        name="bench-agent-tasks",
        scopes=list(VALID_SCOPES),
        expires_days=1,
    )
    return token

def call_mcp(url: str, token: str, tool_name: str, arguments: dict = None) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": f"agent-{tool_name}",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments or {},
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=15.0) as resp:
        t1 = time.perf_counter()
        raw = resp.read()
    data = json.loads(raw.decode("utf-8"))
    elapsed_ms = (t1 - t0) * 1000
    return {
        "latency_ms": elapsed_ms,
        "bytes": len(raw),
        "data": data,
        "success": "result" in data and not data.get("result", {}).get("isError", False),
    }

def benchmark_task(url: str, token: str, task_fn, iterations=5):
    samples = []
    total_bytes = 0
    num_calls = 0
    errors = 0
    for _ in range(iterations):
        t0 = time.perf_counter()
        try:
            calls, b = task_fn(url, token)
            t1 = time.perf_counter()
            samples.append((t1 - t0) * 1000)
            total_bytes = b
            num_calls = calls
        except Exception as e:
            errors += 1
    samples.sort()
    p50 = statistics.median(samples) if samples else 0.0
    p95 = samples[int(len(samples) * 0.95)] if samples else 0.0
    return {
        "calls": num_calls,
        "payload_bytes": total_bytes,
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "errors": errors,
    }

# Task Implementations:
def run_task_a_optimized(url, token):
    res = call_mcp(url, token, "device.snapshot", {})
    return 1, res["bytes"]

def run_task_a_unoptimized(url, token):
    total_b = 0
    # 5 discrete calls
    for tool in ["device.info", "device.battery", "storage.overview", "network.interfaces", "system.inspect"]:
        r = call_mcp(url, token, tool, {})
        total_b += r["bytes"]
    return 5, total_b

def run_task_b(url, token):
    res = call_mcp(url, token, "fs.list", {"workspace_id": "default", "subpath": ""})
    return 1, res["bytes"]

def run_task_c(url, token):
    res = call_mcp(url, token, "fs.search", {"workspace_id": "default", "query": "json"})
    return 1, res["bytes"]

def run_task_d(url, token):
    res = call_mcp(url, token, "process.list", {})
    return 1, res["bytes"]

def run_task_e(url, token):
    res = call_mcp(url, token, "screen.capture", {})
    return 1, res["bytes"]

def run_task_f(url, token):
    res = call_mcp(url, token, "system.health", {})
    return 1, res["bytes"]

def run_all():
    remote_cfg_path = Path.home() / ".tacp" / "remote.json"
    remote_info = json.loads(remote_cfg_path.read_text())
    remote_url = remote_info.get("mcp_endpoint")
    local_url = f"http://127.0.0.1:{remote_info.get('local_port', 8765)}/mcp"
    token = get_token()

    tasks = [
        ("Task A (Device Overview - Optimized)", run_task_a_optimized),
        ("Task A (Device Overview - 5 calls)", run_task_a_unoptimized),
        ("Task B (List Files)", run_task_b),
        ("Task C (Search Files)", run_task_c),
        ("Task D (Process List)", run_task_d),
        ("Task E (Screen Capture)", run_task_e),
        ("Task F (Companion / Health Check)", run_task_f),
    ]

    results = []
    print("Running Agent Task Benchmarks (Local vs Remote)...")
    for name, fn in tasks:
        loc = benchmark_task(local_url, token, fn, iterations=5)
        rem = benchmark_task(remote_url, token, fn, iterations=3)
        results.append({
            "task": name,
            "calls": loc["calls"],
            "payload_bytes": loc["payload_bytes"],
            "local_p50_ms": loc["p50_ms"],
            "local_p95_ms": loc["p95_ms"],
            "remote_p50_ms": rem["p50_ms"],
            "remote_p95_ms": rem["p95_ms"],
            "errors": loc["errors"] + rem["errors"],
        })
        print(f"  {name:38} | Calls: {loc['calls']} | Local P50: {loc['p50_ms']:6.2f} ms | Remote P50: {rem['p50_ms']:6.2f} ms | Bytes: {loc['payload_bytes']}")

    out_file = Path("artifacts/phase2/benchmark_agent_tasks.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2))
    print(f"\nSaved agent task benchmark results to {out_file}")

if __name__ == "__main__":
    run_all()
