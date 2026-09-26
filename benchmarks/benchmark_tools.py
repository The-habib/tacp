"""Benchmark individual tool execution and decompose latency classes."""

from __future__ import annotations

import sys
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
from tacp.domain.audit import AuditEvent
from tacp.infrastructure.config import TacpConfig


def run_benchmark(output_dir: Path) -> List[MetricSummary]:
    config = TacpConfig.load()
    server = create_mcp_server(config=config, enable_device_capabilities=True)
    metrics: List[MetricSummary] = []

    # 1. Warm tool call: system.inspect (via full MCP request envelope)
    req_inspect = McpRequest(
        method="tools/call",
        params={"name": "system.inspect", "arguments": {}},
        id=10,
    )
    d_inspect = time_callable(lambda: server.handle_request(req_inspect), iterations=50)
    metrics.append(compute_metrics("tool_system_inspect_e2e", d_inspect))

    # 2. Warm tool call: system.health
    req_health = McpRequest(
        method="tools/call",
        params={"name": "system.health", "arguments": {}},
        id=11,
    )
    d_health = time_callable(lambda: server.handle_request(req_health), iterations=50)
    metrics.append(compute_metrics("tool_system_health_e2e", d_health))

    # 3. Device info: device.info
    req_devinfo = McpRequest(
        method="tools/call",
        params={"name": "device.info", "arguments": {}},
        id=12,
    )
    d_devinfo = time_callable(lambda: server.handle_request(req_devinfo), iterations=50)
    metrics.append(compute_metrics("tool_device_info_e2e", d_devinfo))

    # 4. Storage overview: storage.overview
    req_storage = McpRequest(
        method="tools/call",
        params={"name": "storage.overview", "arguments": {}},
        id=13,
    )
    d_storage = time_callable(lambda: server.handle_request(req_storage), iterations=30)
    metrics.append(compute_metrics("tool_storage_overview_e2e", d_storage))

    # 5. Device snapshot: device.snapshot (aggregate)
    req_snap = McpRequest(
        method="tools/call",
        params={"name": "device.snapshot", "arguments": {}},
        id=14,
    )
    d_snap = time_callable(lambda: server.handle_request(req_snap), iterations=20)
    metrics.append(compute_metrics("tool_device_snapshot_e2e", d_snap))

    # 6. LATENCY CLASS DECOMPOSITION (for system.inspect):
    # A: Tool name normalization
    d_norm = time_callable(
        lambda: server.tool_registry.normalize_tool_name("system.inspect"), iterations=200
    )
    metrics.append(compute_metrics("latency_class_name_normalization", d_norm))

    # B: Tool execution inside registry (policy + dispatch + audit)
    d_reg_exec = time_callable(
        lambda: server.tool_registry.execute_tool("system.inspect", {}), iterations=50
    )
    metrics.append(compute_metrics("latency_class_registry_execute_tool", d_reg_exec))

    # C: Raw system service (pure Python / uname / /proc without policy or audit)
    d_raw = time_callable(
        lambda: server.tool_registry.system_service.inspect_system(), iterations=100
    )
    metrics.append(compute_metrics("latency_class_raw_system_inspect", d_raw))

    # D: Audit log insert overhead (single audit event with fresh ID)
    def _record_audit_event() -> None:
        ev = AuditEvent(
            capability="system.inspect",
            action="system.inspect",
            policy_decision="ALLOWED",
            result="SUCCESS",
            duration_ms=1,
            principal="test",
            request_id="bench-req",
        )
        server.tool_registry.audit_service.record_event(ev)

    d_audit = time_callable(_record_audit_event, iterations=50)
    metrics.append(compute_metrics("latency_class_audit_record_event", d_audit))

    save_benchmark_result(
        suite_name="benchmark_tools",
        metrics=metrics,
        output_dir=output_dir,
        extra={"rss_mb": get_current_rss_mb()},
    )
    return metrics


if __name__ == "__main__":
    out = Path("artifacts/benchmarks")
    results = run_benchmark(out)
    for m in results:
        print(
            f"{m.name:34} | P50: {m.p50_ms:6.3f} ms | P95: {m.p95_ms:6.3f} ms | Max: {m.max_ms:6.3f} ms"
        )
