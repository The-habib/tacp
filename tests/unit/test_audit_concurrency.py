"""Unit tests for AuditService concurrent append serialization."""

import threading
import uuid
from pathlib import Path

from tacp.core.audit_service import AuditService
from tacp.domain.audit import AuditEvent
from tacp.infrastructure.database import Database


def test_concurrent_audit_appends_preserve_linear_hash_chain(tmp_path: Path) -> None:
    db_path = tmp_path / "audit_concurrency.db"
    db = Database(db_path)
    audit_service = AuditService(db)

    num_threads = 8
    events_per_thread = 15
    total_events = num_threads * events_per_thread

    barrier = threading.Barrier(num_threads)
    errors: list[Exception] = []

    def worker(worker_id: int) -> None:
        try:
            barrier.wait()
            for i in range(events_per_thread):
                event = AuditEvent(
                    id=f"evt-{worker_id}-{i}-{uuid.uuid4().hex[:6]}",
                    capability="workspace.patch",
                    action="patch.apply",
                    policy_decision="ALLOW",
                    result="SUCCESS",
                    duration_ms=10,
                    principal=f"agent-{worker_id}",
                    request_id=f"req-{worker_id}-{i}",
                    workspace_id="ws-concurrency",
                    parameters_redacted={"step": i, "worker": worker_id},
                )
                audit_service.record_event(event)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Encountered errors during concurrent audit append: {errors}"

    # Verify total events count via direct database query
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audit_logs;")
    count = cur.fetchone()[0]
    assert count == total_events

    # Verify cryptographic hash chain across all records
    assert audit_service.verify_integrity() is True
