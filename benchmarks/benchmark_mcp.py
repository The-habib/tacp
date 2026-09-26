"""Benchmark MCP protocol handling, initialization, and tool enumeration."""

from __future__ import annotations

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
    metrics: List[MetricSummary] = []

    # 1. Server Factory Startup
    init_durations: List[int] = []
    for _ in range(20):
        t0 = time.perf_counter_ns()
        srv = create_mcp_server(config=config, enable_device_capabilities=True)
        t1 = time.perf_counter_ns()
        init_durations.append(t1 - t0)
    metrics.append(compute_metrics("mcp_server_factory_creation", init_durations))

    # Shared instance for operational benchmarks
    server = create_mcp_server(config=config, enable_device_capabilities=True)

    # 2. Protocol Handshake (initialize)
    init_req = McpRequest(
        method="initialize",
        params={
            "protocolVersion": "2026-07-28",
            "capabilities": {},
            "clientInfo": {"name": "benchmark_client", "version": "1.0"},
        },
        id=1,
    )
    d_init = time_callable(lambda: server.handle_request(init_req), iterations=100)
    metrics.append(compute_metrics("mcp_initialize_handshake", d_init))

    # 3. Tool Discovery (tools/list)
    tools_req = McpRequest(method="tools/list", params={}, id=2)
    d_tools = time_callable(lambda: server.handle_request(tools_req), iterations=50)
    metrics.append(compute_metrics("mcp_tools_list_dispatch", d_tools))

    # 4. Resources Discovery (resources/list)
    res_req = McpRequest(method="resources/list", params={}, id=3)
    d_res = time_callable(lambda: server.handle_request(res_req), iterations=50)
    metrics.append(compute_metrics("mcp_resources_list_dispatch", d_res))

    # 5. Prompts Discovery (prompts/list)
    prm_req = McpRequest(method="prompts/list", params={}, id=4)
    d_prm = time_callable(lambda: server.handle_request(prm_req), iterations=50)
    metrics.append(compute_metrics("mcp_prompts_list_dispatch", d_prm))

    # 6. Low-level JSON serialization of tools response
    sample_resp = server.handle_request(tools_req)
    if sample_resp:
        d_ser = time_callable(lambda: sample_resp.to_json(), iterations=100)
        metrics.append(compute_metrics("mcp_tools_list_serialization", d_ser))

    save_benchmark_result(
        suite_name="benchmark_mcp",
        metrics=metrics,
        output_dir=output_dir,
        extra={
            "tools_count": len(server.tool_registry.list_tools()),
            "rss_mb": get_current_rss_mb(),
        },
    )
    return metrics


if __name__ == "__main__":
    out = Path("artifacts/benchmarks")
    results = run_benchmark(out)
    for m in results:
        print(
            f"{m.name:32} | P50: {m.p50_ms:6.3f} ms | P95: {m.p95_ms:6.3f} ms | Max: {m.max_ms:6.3f} ms"
        )
