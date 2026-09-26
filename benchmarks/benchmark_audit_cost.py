"""Phase 11 Audit Performance Benchmark.

Measures:
1. Read request with audit
2. Read request without audit
3. Mutation with audit
4. High-frequency read workload
"""

import tempfile
import time
import json
import threading
from pathlib import Path
from tacp.infrastructure.database import Database
from tacp.core.audit_service import AuditService, compute_audit_entry_hash, GENESIS_HASH
from tacp.domain.audit import AuditEvent

def run_benchmark():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "bench_audit.db"
        db = Database(db_path)
        service = AuditService(db)

        # Warm up
        evt = AuditEvent(
            capability="fs.read",
            action="read",
            policy_decision="ALLOW",
            result="SUCCESS",
            duration_ms=1,
            principal="bench-agent",
            parameters_redacted={"path": "/test"},
        )
        service.record_event(evt)

        # 1. Sequential Audit Appends (simulating tool execution)
        N = 300
        start = time.perf_counter()
        for i in range(N):
            service.record_event(AuditEvent(
                capability="fs.read",
                action="read",
                policy_decision="ALLOW",
                result="SUCCESS",
                duration_ms=1,
                principal="bench-agent",
                parameters_redacted={"step": i},
            ))
        elapsed = time.perf_counter() - start
        seq_per_op = (elapsed / N) * 1000
        seq_throughput = N / elapsed

        # 2. In-memory hash computation alone
        start = time.perf_counter()
        prev = GENESIS_HASH
        for i in range(N):
            prev = compute_audit_entry_hash(
                prev_hash=prev,
                id=f"evt-{i}",
                timestamp="2026-09-26T12:00:00Z",
                request_id="req-1",
                principal="bench-agent",
                capability="fs.read",
                workspace_id=None,
                action="read",
                policy_decision="ALLOW",
                result="SUCCESS",
                duration_ms=1,
                parameters_json='{"step": 1}',
            )
        elapsed_hash = time.perf_counter() - start
        hash_per_op = (elapsed_hash / N) * 1000

        # 3. Concurrent Audit Appends (10 threads)
        num_threads = 10
        events_per_thread = 30
        barrier = threading.Barrier(num_threads)
        start_concurrent = time.perf_counter()
        def worker(wid):
            barrier.wait()
            for i in range(events_per_thread):
                service.record_event(AuditEvent(
                    capability="fs.read",
                    action="read",
                    policy_decision="ALLOW",
                    result="SUCCESS",
                    duration_ms=1,
                    principal=f"agent-{wid}",
                    parameters_redacted={"step": i},
                ))
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed_concurrent = time.perf_counter() - start_concurrent
        conc_throughput = (num_threads * events_per_thread) / elapsed_concurrent

        print(f"=== AUDIT COST BREAKDOWN (N={N}) ===")
        print(f"Cryptographic Hash computation: {hash_per_op:.4f} ms/op ({N/elapsed_hash:.0f} ops/sec)")
        print(f"Full SQLite Audit record_event: {seq_per_op:.4f} ms/op ({seq_throughput:.0f} ops/sec)")
        print(f"SQLite overhead per event:      {seq_per_op - hash_per_op:.4f} ms ({(seq_per_op - hash_per_op)/seq_per_op*100:.1f}% of total)")
        print(f"Concurrent Audit Throughput (10T): {conc_throughput:.1f} ops/sec")

if __name__ == "__main__":
    run_benchmark()
