#!/usr/bin/env python3
"""Deterministic Performance Measurement Script for TACP 0.1.

Measures latency and memory distributions across >= 30 iterations:
- Cold startup time (subprocess spawn of `tacp version`)
- Memory RSS at rest (MB)
- fs.read latency (ms)
- fs.list latency (ms)
- fs.search latency (ms)
- process.list latency (ms)
- MCP stdio round-trip latency (ms)
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import create_mcp_server
from tacp.infrastructure.config import TacpConfig


def get_rss_mb() -> float:
    """Read current process Resident Set Size in MB from /proc/self/statm or resource."""
    try:
        statm_path = Path("/proc/self/statm")
        if statm_path.exists():
            parts = statm_path.read_text().split()
            pages = int(parts[1])
            page_size = 4096
            return (pages * page_size) / (1024 * 1024)
    except (OSError, ValueError):
        pass
    import resource

    # ru_maxrss in kilobytes on Linux
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def benchmark_iterations(
    name: str,
    fn: Callable[[], Any],
    iterations: int = 30,
) -> Dict[str, float]:
    latencies: List[float] = []
    # Warmup
    fn()

    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)  # ms

    latencies.sort()
    p95_idx = int(len(latencies) * 0.95)
    return {
        "min_ms": round(latencies[0], 2),
        "median_ms": round(statistics.median(latencies), 2),
        "p95_ms": round(latencies[p95_idx], 2),
        "max_ms": round(latencies[-1], 2),
        "mean_ms": round(statistics.mean(latencies), 2),
    }


def main() -> int:
    iterations = 35
    print(f"[*] Running TACP 0.1 Performance Benchmarks ({iterations} iterations per metric)...")

    repo_root = Path(__file__).resolve().parent.parent
    tacp_bin = repo_root / ".venv" / "bin" / "tacp"

    # 1. Cold Startup Time
    startup_latencies: List[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        res = subprocess.run([str(tacp_bin), "version"], capture_output=True)
        t1 = time.perf_counter()
        if res.returncode != 0:
            print(f"[!] Error in cold startup benchmark: {res.stderr}")
            return 1
        startup_latencies.append((t1 - t0) * 1000.0)

    startup_latencies.sort()
    startup_p95_idx = int(len(startup_latencies) * 0.95)
    startup_stats = {
        "min_ms": round(startup_latencies[0], 2),
        "median_ms": round(statistics.median(startup_latencies), 2),
        "p95_ms": round(startup_latencies[startup_p95_idx], 2),
        "max_ms": round(startup_latencies[-1], 2),
        "mean_ms": round(statistics.mean(startup_latencies), 2),
    }

    # 2. In-Process Server Setup
    config = TacpConfig.load()
    server = create_mcp_server(config)
    tools = server.tool_registry
    workspaces = tools.workspace_service.list_workspaces()
    if not workspaces:
        ws = tools.workspace_service.register_workspace("tacp", repo_root)
        ws_id = ws.id
    else:
        ws_id = workspaces[0]["id"]

    # 3. Memory RSS at rest
    rss_measurements: List[float] = []
    for _ in range(iterations):
        rss_measurements.append(get_rss_mb())
        time.sleep(0.01)

    rss_measurements.sort()
    rss_p95_idx = int(len(rss_measurements) * 0.95)
    rss_stats = {
        "min_mb": round(rss_measurements[0], 2),
        "median_mb": round(statistics.median(rss_measurements), 2),
        "p95_mb": round(rss_measurements[rss_p95_idx], 2),
        "max_mb": round(rss_measurements[-1], 2),
    }

    # 4. fs.read benchmark
    fs_read_stats = benchmark_iterations(
        "fs.read",
        lambda: tools.execute_tool("fs.read", {"workspace_id": ws_id, "subpath": "README.md"}),
        iterations=iterations,
    )

    # 5. fs.list benchmark
    fs_list_stats = benchmark_iterations(
        "fs.list",
        lambda: tools.execute_tool("fs.list", {"workspace_id": ws_id, "subpath": ""}),
        iterations=iterations,
    )

    # 6. fs.search benchmark
    fs_search_stats = benchmark_iterations(
        "fs.search",
        lambda: tools.execute_tool("fs.search", {"workspace_id": ws_id, "query": "TACP"}),
        iterations=iterations,
    )

    # 7. process.list benchmark
    proc_list_stats = benchmark_iterations(
        "process.list",
        lambda: tools.execute_tool("process.list", {}),
        iterations=iterations,
    )

    # 8. MCP handle_request round-trip
    mcp_ping_req = McpRequest(method="ping", params={}, id=999)
    mcp_ping_stats = benchmark_iterations(
        "mcp.ping",
        lambda: server.handle_request(mcp_ping_req),
        iterations=iterations,
    )

    mcp_call_req = McpRequest(
        method="tools/call",
        params={"name": "system.version", "arguments": {}},
        id=1000,
    )
    mcp_call_stats = benchmark_iterations(
        "mcp.tools/call",
        lambda: server.handle_request(mcp_call_req),
        iterations=iterations,
    )

    results = {
        "metadata": {
            "platform": sys.platform,
            "python_version": sys.version.split()[0],
            "iterations": iterations,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "cold_startup_ms": startup_stats,
        "memory_rss_mb": rss_stats,
        "fs_read_ms": fs_read_stats,
        "fs_list_ms": fs_list_stats,
        "fs_search_ms": fs_search_stats,
        "process_list_ms": proc_list_stats,
        "mcp_ping_ms": mcp_ping_stats,
        "mcp_call_ms": mcp_call_stats,
    }

    # Save to JSON
    out_file = repo_root / "docs" / "testing" / "PERFORMANCE-RESULTS.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2))

    # Print Markdown Summary
    print("\n============================================================")
    print(" TACP 0.1 EMPIRICAL BENCHMARK RESULTS (N=35)")
    print("============================================================")
    print("| Metric | Min | Median | P95 | Max | Unit |")
    print("|---|---|---|---|---|---|")
    print(
        f"| Cold CLI Startup (`tacp version`) | "
        f"{startup_stats['min_ms']} | {startup_stats['median_ms']} | "
        f"{startup_stats['p95_ms']} | {startup_stats['max_ms']} | ms |"
    )
    print(
        f"| Memory RSS at rest | "
        f"{rss_stats['min_mb']} | {rss_stats['median_mb']} | "
        f"{rss_stats['p95_mb']} | {rss_stats['max_mb']} | MB |"
    )
    print(
        f"| `fs.read` latency | "
        f"{fs_read_stats['min_ms']} | {fs_read_stats['median_ms']} | "
        f"{fs_read_stats['p95_ms']} | {fs_read_stats['max_ms']} | ms |"
    )
    print(
        f"| `fs.list` latency | "
        f"{fs_list_stats['min_ms']} | {fs_list_stats['median_ms']} | "
        f"{fs_list_stats['p95_ms']} | {fs_list_stats['max_ms']} | ms |"
    )
    print(
        f"| `fs.search` latency | "
        f"{fs_search_stats['min_ms']} | {fs_search_stats['median_ms']} | "
        f"{fs_search_stats['p95_ms']} | {fs_search_stats['max_ms']} | ms |"
    )
    print(
        f"| `process.list` latency | "
        f"{proc_list_stats['min_ms']} | {proc_list_stats['median_ms']} | "
        f"{proc_list_stats['p95_ms']} | {proc_list_stats['max_ms']} | ms |"
    )
    print(
        f"| MCP `ping` round-trip | "
        f"{mcp_ping_stats['min_ms']} | {mcp_ping_stats['median_ms']} | "
        f"{mcp_ping_stats['p95_ms']} | {mcp_ping_stats['max_ms']} | ms |"
    )
    print(
        f"| MCP `tools/call` round-trip | "
        f"{mcp_call_stats['min_ms']} | {mcp_call_stats['median_ms']} | "
        f"{mcp_call_stats['p95_ms']} | {mcp_call_stats['max_ms']} | ms |"
    )
    print("============================================================\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
