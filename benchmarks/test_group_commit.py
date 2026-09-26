import tempfile
import time
import json
import threading
import sqlite3
from pathlib import Path
from tacp.infrastructure.database import Database
from tacp.core.audit_service import AuditService, compute_audit_entry_hash, GENESIS_HASH
from tacp.domain.audit import AuditEvent
from tacp.infrastructure.logging import redact_dict

class BatchedAuditService(AuditService):
    def __init__(self, db: Database) -> None:
        super().__init__(db)
        self._lock = threading.Lock()
        self._queue_lock = threading.Lock()
        self._pending_queue = []

    def record_event(self, event: AuditEvent) -> str:
        clean_params = redact_dict(event.parameters_redacted)
        params_json = json.dumps(clean_params, sort_keys=True)
        
        # [event, done_event, entry_hash, exc, params_json]
        item = [event, threading.Event(), None, None, params_json]
        
        with self._queue_lock:
            self._pending_queue.append(item)
            is_leader = len(self._pending_queue) == 1

        if not is_leader:
            item[1].wait()
            if item[3] is not None:
                raise item[3]
            return item[2]

        # Leader drains the queue
        with self._lock:
            while True:
                with self._queue_lock:
                    if not self._pending_queue:
                        break
                    batch = self._pending_queue
                    self._pending_queue = []

                conn = self.db.connect()
                conn.execute("BEGIN IMMEDIATE;")
                try:
                    if self._latest_entry_hash is None:
                        cursor = conn.cursor()
                        cursor.execute("SELECT entry_hash FROM audit_logs ORDER BY rowid DESC LIMIT 1;")
                        row = cursor.fetchone()
                        prev_hash = row["entry_hash"] if row and row["entry_hash"] else GENESIS_HASH
                    else:
                        prev_hash = self._latest_entry_hash

                    rows_to_insert = []
                    for it in batch:
                        evt = it[0]
                        p_json = it[4]
                        entry_hash = compute_audit_entry_hash(
                            prev_hash=prev_hash,
                            id=evt.id,
                            timestamp=evt.timestamp,
                            request_id=evt.request_id,
                            principal=evt.principal,
                            capability=evt.capability,
                            workspace_id=evt.workspace_id,
                            action=evt.action,
                            policy_decision=evt.policy_decision,
                            result=evt.result,
                            duration_ms=evt.duration_ms,
                            parameters_json=p_json,
                        )
                        rows_to_insert.append((
                            evt.id, evt.timestamp, evt.request_id, evt.principal,
                            evt.capability, evt.workspace_id, evt.action,
                            evt.policy_decision, evt.result, evt.duration_ms,
                            p_json, prev_hash, entry_hash
                        ))
                        it[2] = entry_hash
                        prev_hash = entry_hash

                    conn.executemany(
                        """
                        INSERT INTO audit_logs (
                            id, timestamp, request_id, principal, capability,
                            workspace_id, action, policy_decision, result,
                            duration_ms, parameters_json, prev_hash, entry_hash
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        rows_to_insert,
                    )
                    conn.commit()
                    self._latest_entry_hash = prev_hash
                    for it in batch:
                        it[1].set()
                except Exception as exc:
                    conn.rollback()
                    self._latest_entry_hash = None
                    for it in batch:
                        it[3] = exc
                        it[1].set()
                    if item[3] is not None:
                        raise item[3]
                    raise

            if item[3] is not None:
                raise item[3]
            return item[2]

def run():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "bench.db"
        db = Database(db_path)
        service = BatchedAuditService(db)

        num_threads = 10
        events_per_thread = 50
        barrier = threading.Barrier(num_threads)
        start = time.perf_counter()

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
        for t in threads: t.start()
        for t in threads: t.join()

        elapsed = time.perf_counter() - start
        total_events = num_threads * events_per_thread
        throughput = total_events / elapsed
        print(f"BatchedAuditService 10-thread throughput: {throughput:.1f} ops/sec in {elapsed:.3f}s")
        assert service.verify_integrity() is True
        print("Cryptographic integrity verification: 100% PASSED!")

if __name__ == "__main__":
    run()
