"""Phase 3 Local Systems Benchmark Suite.

Executes all 14 required local primitives using standardized statistical sampling:
1. MCP initialize
2. tools/list
3. resources/list
4. prompts/list
5. tools/call
6. authentication
7. policy evaluation
8. audit
9. filesystem
10. process
11. companion
12. device state
13. device snapshot
14. screen capture
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from benchmarks.phase3.harness import BenchmarkRunner, BenchmarkResult
from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import create_mcp_server
from tacp.control.auth import TokenService, VALID_SCOPES
from tacp.control.identity import Principal, RequestContext
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService, compute_audit_entry_hash, GENESIS_HASH
from tacp.core.capability_service import CapabilityService
from tacp.core.discovery import DeviceDiscovery
from tacp.core.state import DeviceStateManager
from tacp.domain.audit import AuditEvent
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database
from tacp.backends.base import BackendType

def run_local_benchmarks() -> list[BenchmarkResult]:
    results: list[BenchmarkResult] = []
    server = create_mcp_server(enable_device_capabilities=True)
    cfg = TacpConfig.load()
    db = Database(cfg.db_path)
    ts = TokenService(db)
    policy = PolicyEngine()
    audit = AuditService(db)
    state_mgr = DeviceStateManager()
    discovery = DeviceDiscovery()

    # Create a test token for auth bench
    _, token = ts.create_token(name="local-bench-token", scopes=list(VALID_SCOPES), expires_days=1)

    print("Running Local Benchmarks...")

    # 1. MCP initialize
    req_init = McpRequest(method="initialize", params={"protocolVersion": "2026-07-28"}, id=1)
    res_init = BenchmarkRunner.run(
        "mcp.initialize", "local", "warm",
        lambda: server.handle_request(req_init),
        samples=50, warmup=10,
    )
    results.append(res_init)

    # 2. tools/list
    res_tools = BenchmarkRunner.run(
        "mcp.tools_list", "local", "warm",
        lambda: server.tool_registry.list_tools(),
        samples=50, warmup=10,
    )
    results.append(res_tools)

    # 3. resources/list
    req_res = McpRequest(method="resources/list", params={}, id=2)
    res_resources = BenchmarkRunner.run(
        "mcp.resources_list", "local", "warm",
        lambda: server.handle_request(req_res),
        samples=50, warmup=10,
    )
    results.append(res_resources)

    # 4. prompts/list
    req_prompts = McpRequest(method="prompts/list", params={}, id=3)
    res_prompts = BenchmarkRunner.run(
        "mcp.prompts_list", "local", "warm",
        lambda: server.handle_request(req_prompts),
        samples=50, warmup=10,
    )
    results.append(res_prompts)

    # 5. tools/call (system.inspect)
    req_call = McpRequest(method="tools/call", params={"name": "system.inspect", "arguments": {}}, id=4)
    res_call = BenchmarkRunner.run(
        "mcp.tools_call_system_inspect", "local", "warm",
        lambda: server.handle_request(req_call),
        samples=30, warmup=5,
    )
    results.append(res_call)

    # 6. Authentication (token validation)
    res_auth = BenchmarkRunner.run(
        "auth.validate_token", "local", "warm",
        lambda: ts.validate_token(token),
        samples=50, warmup=10,
    )
    results.append(res_auth)

    # 7. Policy evaluation
    principal = Principal.local_agent("test-agent")
    ctx = RequestContext(capability="fs.read", principal=principal, request_id="req-test")
    res_policy = BenchmarkRunner.run(
        "policy.evaluate_request", "local", "warm",
        lambda: policy.evaluate_request(ctx),
        samples=50, warmup=10,
    )
    results.append(res_policy)

    # 8. Audit append & hash chain
    import uuid
    def record_audit():
        evt = AuditEvent(
            id=f"evt-{uuid.uuid4().hex[:12]}",
            capability="fs.read", action="read", policy_decision="ALLOW",
            result="SUCCESS", duration_ms=1, principal="agent-bench",
            parameters_redacted={"file": "test"},
        )
        return audit.record_event(evt)

    res_audit = BenchmarkRunner.run(
        "audit.record_event", "local", "warm",
        record_audit,
        samples=20, warmup=5,
    )
    results.append(res_audit)

    # 9. Filesystem stat
    res_fs = BenchmarkRunner.run(
        "filesystem.stat_home", "local", "warm",
        lambda: os.stat(str(Path.home())),
        samples=50, warmup=10,
    )
    results.append(res_fs)

    # 10. Process list inspection
    res_proc = BenchmarkRunner.run(
        "process.list", "local", "warm",
        lambda: server.tool_registry.execute_tool("process.list", {}),
        samples=15, warmup=3,
    )
    results.append(res_proc)

    # 11. Companion probe
    backend_comp = server.tool_registry.device_registry.backend_manager.get_backend(BackendType.ANDROID_BRIDGE) if server.tool_registry.device_registry else None
    res_comp = BenchmarkRunner.run(
        "companion.probe_status", "local", "warm",
        lambda: backend_comp.probe(force=False) if backend_comp else None,
        samples=50, warmup=10,
    )
    results.append(res_comp)

    # 12. Device state memory read
    res_state = BenchmarkRunner.run(
        "device_state.get_runtime", "local", "hit",
        lambda: state_mgr.get_runtime(force=False),
        samples=50, warmup=10,
    )
    results.append(res_state)

    # 13. Device snapshot (aggregate)
    res_snap = BenchmarkRunner.run(
        "device.snapshot", "local", "warm",
        lambda: server.tool_registry.execute_tool("device.snapshot", {}),
        samples=30, warmup=5,
    )
    results.append(res_snap)

    # 14. Screen capture handler
    res_screen = BenchmarkRunner.run(
        "screen.capture", "local", "warm",
        lambda: server.tool_registry.execute_tool("screen.capture", {}),
        samples=30, warmup=5,
    )
    results.append(res_screen)

    for r in results:
        print(f"  {r.name:32} | P50: {r.p50_ms:6.3f} ms | P95: {r.p95_ms:6.3f} ms | P99: {r.p99_ms:6.3f} ms | Ops/sec: {r.throughput_ops_sec:7.1f} | Errors: {r.error_rate}")

    return results

if __name__ == "__main__":
    out_dir = Path("artifacts/phase3")
    out_dir.mkdir(parents=True, exist_ok=True)
    res = run_local_benchmarks()
    (out_dir / "benchmarks_local.json").write_text(json.dumps([r.to_dict() for r in res], indent=2))
    print(f"\nSaved local benchmark results to {out_dir / 'benchmarks_local.json'}")
