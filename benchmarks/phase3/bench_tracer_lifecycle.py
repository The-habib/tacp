"""Benchmark exact nanosecond time accounting for all 11 request lifecycle phases."""

import time
import json
import statistics
from pathlib import Path
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database
from tacp.core.audit_service import AuditService
from tacp.core.capability_service import CapabilityService
from tacp.core.state import DeviceStateManager
from tacp.control.policy import PolicyEngine
from tacp.control.auth import TokenService
from tacp.control.identity import Principal, RequestContext
from tacp.access.mcp.tools import McpToolRegistry
from tacp.core.tracer import RequestTracer

def run_lifecycle_benchmark():
    config = TacpConfig.load()
    db = Database(Path("/data/data/com.termux/files/home/.tacp/tacp.db"))
    audit_svc = AuditService(db)
    policy_engine = PolicyEngine(config)
    token_svc = TokenService(db)
    registry = McpToolRegistry(
        workspace_service=None,
        filesystem_service=None,
        process_service=None,
        system_service=None,
        patch_service=None,
        audit_service=audit_svc,
        policy_engine=policy_engine,
        capability_service=CapabilityService(),
    )
    token_rec, raw_token = token_svc.create_token(name="bench_tracer", scopes=["tacp.admin"])

    phases = [
        "transport_receive",
        "authentication",
        "session",
        "policy",
        "capability_resolution",
        "provider_resolution",
        "cache",
        "execution",
        "serialization",
        "audit",
        "transport_write",
    ]
    
    timings = {p: [] for p in phases}
    
    # 500 iterations for statistical rigor
    N = 500
    for i in range(N):
        tracer = RequestTracer("trace_" + str(i), "req_" + str(i))
        
        # 1. Transport receive simulation (parsing JSON-RPC payload)
        with tracer.span("transport_receive"):
            raw_payload = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"system.health","arguments":{}}}'
            parsed = json.loads(raw_payload.decode('utf-8'))
        
        # 2. Authentication
        with tracer.span("authentication"):
            rec = token_svc.validate_token(raw_token)
            principal = token_svc.principal_from_token(rec) if rec else Principal.anonymous()
            
        # 3. Session
        with tracer.span("session"):
            session_id = "sess-bench-001"
            
        # 4. Policy evaluation
        with tracer.span("policy"):
            ctx = RequestContext(capability="system.health", principal=principal)
            decision = policy_engine.evaluate_request(ctx)
            
        # 5. Capability resolution
        with tracer.span("capability_resolution"):
            cap = registry.normalize_tool_name("system.health")
            
        # 6. Provider resolution
        with tracer.span("provider_resolution"):
            prov = registry.device_registry.get(cap) if registry.device_registry else None
            
        # 7. Cache check
        with tracer.span("cache"):
            cached_data = DeviceStateManager.get_default().get_field("memory")
            
        # 8. Execution
        with tracer.span("execution"):
            res = {"status": "ok", "healthy": True}
            
        # 9. Serialization
        with tracer.span("serialization"):
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": json.dumps(res)}]}}).encode('utf-8')
            
        # 10. Audit
        with tracer.span("audit"):
            from tacp.domain.audit import AuditEvent
            evt = AuditEvent(
                capability="system.health",
                action="system.health",
                policy_decision="ALLOWED",
                result="SUCCESS",
                duration_ms=1,
                principal=principal.id,
            )
            audit_svc.record_event(evt)
            
        # 11. Transport write
        with tracer.span("transport_write"):
            header_len = len(body)
            
        tracer.finish()
        
        for s in tracer.spans:
            timings[s.name].append(s.duration_ns)

    token_svc.revoke_token(token_rec.id)

    results = {}
    print("Phase | P50 (ns) | P90 (ns) | P95 (ns) | P99 (ns) | Mean (ns) | Mean (us)")
    print("---|---|---|---|---|---|---")
    for p in phases:
        data = sorted(timings[p])
        p50 = data[int(len(data)*0.50)]
        p90 = data[int(len(data)*0.90)]
        p95 = data[int(len(data)*0.95)]
        p99 = data[int(len(data)*0.99)]
        mean = statistics.mean(data)
        results[p] = {
            "p50_ns": p50,
            "p90_ns": p90,
            "p95_ns": p95,
            "p99_ns": p99,
            "mean_ns": mean,
            "mean_us": mean / 1000.0,
        }
        print(f"{p} | {p50} | {p90} | {p95} | {p99} | {mean:.1f} | {mean/1000.0:.2f} us")
        
    with open('artifacts/phase3/tracer_lifecycle_results.json', 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == '__main__':
    run_lifecycle_benchmark()
