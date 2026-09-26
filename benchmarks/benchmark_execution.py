"""Benchmark process execution, allowlist checking, and command dispatch."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.common import (
    MetricSummary,
    compute_metrics,
    get_current_rss_mb,
    save_benchmark_result,
    time_callable,
)
from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import create_mcp_server
from tacp.infrastructure.config import TacpConfig


def run_benchmark(output_dir: Path) -> List[MetricSummary]:
    config = TacpConfig.load()
    server = create_mcp_server(config=config, enable_device_capabilities=True)
    metrics: List[MetricSummary] = []

    # 1. Raw OS subprocess execution (python subprocess.run)
    d_raw_subproc = time_callable(
        lambda: subprocess.run(["echo", "benchmark"], capture_output=True, text=True, check=True),
        iterations=30,
    )
    metrics.append(compute_metrics("exec_raw_subprocess_echo", d_raw_subproc))

    # 2. Process list: process.list (reading /proc)
    req_plist = McpRequest(
        method="tools/call",
        params={"name": "process.list", "arguments": {}},
        id=30,
    )
    d_plist = time_callable(lambda: server.handle_request(req_plist), iterations=20)
    metrics.append(compute_metrics("exec_process_list_e2e", d_plist))

    # 3. Direct ProcessService.list_processes()
    d_raw_plist = time_callable(lambda: server.tool_registry.process_service.list_processes(), iterations=20)
    metrics.append(compute_metrics("exec_raw_process_service_list", d_raw_plist))

    # 4. Process inspect: inspect current pid
    req_pinspect = McpRequest(
        method="tools/call",
        params={"name": "process.inspect", "arguments": {"pid": sys.executable}},
        id=31,
    )

    save_benchmark_result(
        suite_name="benchmark_execution",
        metrics=metrics,
        output_dir=output_dir,
        extra={"rss_mb": get_current_rss_mb()},
    )
    return metrics


if __name__ == "__main__":
    out = Path("artifacts/benchmarks")
    results = run_benchmark(out)
    for m in results:
        print(f"{m.name:34} | P50: {m.p50_ms:6.3f} ms | P95: {m.p95_ms:6.3f} ms | Max: {m.max_ms:6.3f} ms")
