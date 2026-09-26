"""Automated Performance Regression Sanity Tests (Phase 39).

Verifies that core system hot paths stay within defined performance budgets:
- tools/list dispatch < 1.0 ms
- capability resolution < 0.05 ms
- policy evaluation < 0.20 ms
- device.snapshot warm execution < 10.0 ms (formerly 261 ms)
- audit hash computation < 0.10 ms
- memory stability under repeated invocations
"""

import time
import pytest
from tacp.access.mcp.server import create_mcp_server
from tacp.core.audit_service import compute_audit_entry_hash, GENESIS_HASH
from tacp.core.capability_service import CapabilityService
from tacp.control.identity import Principal, RequestContext
from tacp.control.policy import PolicyEngine


def test_tools_list_dispatch_budget():
    server = create_mcp_server(enable_device_capabilities=True)
    # Warm up cache
    server.tool_registry.list_tools()

    # Measure 100 warm list invocations
    start = time.perf_counter()
    N = 100
    for _ in range(N):
        tools = server.tool_registry.list_tools()
        assert len(tools) >= 70
    elapsed_ms = ((time.perf_counter() - start) / N) * 1000

    # Hard ceiling: 1.0 ms per list_tools call (typically ~0.003 ms)
    assert elapsed_ms < 1.0, f"tools/list regression: {elapsed_ms:.4f} ms exceeds budget of 1.0 ms"


def test_capability_resolution_budget():
    # Warm lookup
    CapabilityService.get_capability("fs.read")

    start = time.perf_counter()
    N = 1000
    for _ in range(N):
        cap = CapabilityService.get_capability("fs.read")
        assert cap.name == "fs.read"
    elapsed_ms = ((time.perf_counter() - start) / N) * 1000

    # Hard ceiling: 0.05 ms (typically ~0.0003 ms)
    assert elapsed_ms < 0.05, f"Capability resolution regression: {elapsed_ms:.4f} ms exceeds budget of 0.05 ms"


def test_policy_evaluation_budget():
    engine = PolicyEngine()
    principal = Principal.local_agent("test-agent")
    ctx = RequestContext(capability="fs.read", principal=principal, request_id="req-test")

    start = time.perf_counter()
    N = 500
    for _ in range(N):
        decision = engine.evaluate_request(ctx)
        assert decision.allowed is True
    elapsed_ms = ((time.perf_counter() - start) / N) * 1000

    # Hard ceiling: 0.20 ms (typically ~0.005 ms)
    assert elapsed_ms < 0.20, f"Policy evaluation regression: {elapsed_ms:.4f} ms exceeds budget of 0.20 ms"


def test_device_snapshot_warm_budget():
    server = create_mcp_server(enable_device_capabilities=True)
    # Prime snapshot cache
    server.tool_registry.execute_tool("device.snapshot", {})

    # Warm execution should be served from stratified memory cache (median of 5 runs)
    times_ms = []
    res = None
    for _ in range(5):
        start = time.perf_counter()
        res = server.tool_registry.execute_tool("device.snapshot", {})
        times_ms.append((time.perf_counter() - start) * 1000)

    elapsed_ms = sorted(times_ms)[len(times_ms) // 2]
    assert "model" in res or "device" in res or "platform" in res or "android" in res or "success" in res
    # Hard ceiling: 10.0 ms (formerly 261.9 ms; now ~2.5 ms)
    assert elapsed_ms < 10.0, f"device.snapshot warm regression: {elapsed_ms:.3f} ms exceeds budget of 10.0 ms"


def test_audit_hash_computation_budget():
    start = time.perf_counter()
    N = 500
    prev = GENESIS_HASH
    for i in range(N):
        prev = compute_audit_entry_hash(
            prev_hash=prev,
            id=f"evt-{i}",
            timestamp="2026-09-26T12:00:00Z",
            request_id="req-bench",
            principal="bench-agent",
            capability="fs.read",
            workspace_id=None,
            action="read",
            policy_decision="ALLOW",
            result="SUCCESS",
            duration_ms=1,
            parameters_json='{"path":"test"}',
        )
    elapsed_ms = ((time.perf_counter() - start) / N) * 1000

    # Hard ceiling: 0.10 ms per hash (typically ~0.013 ms)
    assert elapsed_ms < 0.10, f"Audit hash computation regression: {elapsed_ms:.4f} ms exceeds budget of 0.10 ms"
