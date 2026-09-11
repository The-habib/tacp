import hashlib
import json
import threading
from typing import Any, Dict, List, Optional

from tacp.domain.audit import AuditEvent
from tacp.infrastructure.database import Database
from tacp.infrastructure.logging import redact_dict

GENESIS_HASH = "0" * 64


def compute_audit_entry_hash(
    prev_hash: str,
    id: str,
    timestamp: str,
    request_id: str,
    principal: str,
    capability: str,
    workspace_id: Optional[str],
    action: str,
    policy_decision: str,
    result: str,
    duration_ms: int,
    parameters_json: str,
) -> str:
    """Compute canonical SHA-256 hash for an audit log entry chained to prev_hash."""
    payload = {
        "prev_hash": prev_hash,
        "id": id,
        "timestamp": timestamp,
        "request_id": request_id,
        "principal": principal,
        "capability": capability,
        "workspace_id": workspace_id or "",
        "action": action,
        "policy_decision": policy_decision,
        "result": result,
        "duration_ms": duration_ms,
        "parameters_json": parameters_json,
    }
    canonical_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


class AuditService:
    _lock = threading.Lock()

    def __init__(self, db: Database) -> None:
        self.db = db

    def record_event(self, event: AuditEvent) -> str:
        """Record an audit event and link it into the tamper-evident hash chain."""
        clean_params = redact_dict(event.parameters_redacted)
        params_json = json.dumps(clean_params, sort_keys=True)

        with self._lock:
            conn = self.db.connect()
            conn.execute("BEGIN IMMEDIATE;")
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT entry_hash FROM audit_logs ORDER BY rowid DESC LIMIT 1;")
                row = cursor.fetchone()
                prev_hash = row["entry_hash"] if row and row["entry_hash"] else GENESIS_HASH

                entry_hash = compute_audit_entry_hash(
                    prev_hash=prev_hash,
                    id=event.id,
                    timestamp=event.timestamp,
                    request_id=event.request_id,
                    principal=event.principal,
                    capability=event.capability,
                    workspace_id=event.workspace_id,
                    action=event.action,
                    policy_decision=event.policy_decision,
                    result=event.result,
                    duration_ms=event.duration_ms,
                    parameters_json=params_json,
                )

                conn.execute(
                    """
                    INSERT INTO audit_logs (
                        id, timestamp, request_id, principal, capability,
                        workspace_id, action, policy_decision, result,
                        duration_ms, parameters_json, prev_hash, entry_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        event.id,
                        event.timestamp,
                        event.request_id,
                        event.principal,
                        event.capability,
                        event.workspace_id,
                        event.action,
                        event.policy_decision,
                        event.result,
                        event.duration_ms,
                        params_json,
                        prev_hash,
                        entry_hash,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return entry_hash

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, request_id, principal, capability,
                   workspace_id, action, policy_decision, result,
                   duration_ms, parameters_json, prev_hash, entry_hash
            FROM audit_logs
            ORDER BY timestamp DESC, rowid DESC
            LIMIT ?;
            """,
            (max(1, min(limit, 100)),),
        )
        rows = cursor.fetchall()
        events = []
        for r in rows:
            events.append(
                {
                    "id": r["id"],
                    "timestamp": r["timestamp"],
                    "request_id": r["request_id"],
                    "principal": r["principal"],
                    "capability": r["capability"],
                    "workspace_id": r["workspace_id"],
                    "action": r["action"],
                    "policy_decision": r["policy_decision"],
                    "result": r["result"],
                    "duration_ms": r["duration_ms"],
                    "parameters": json.loads(r["parameters_json"]),
                    "prev_hash": r["prev_hash"],
                    "entry_hash": r["entry_hash"],
                }
            )
        return events

    def verify_integrity(self) -> bool:
        """Verify the cryptographic hash chain and structural integrity of all audit records."""
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, request_id, principal, capability,
                   workspace_id, action, policy_decision, result,
                   duration_ms, parameters_json, prev_hash, entry_hash
            FROM audit_logs
            ORDER BY rowid ASC;
            """
        )
        rows = cursor.fetchall()
        expected_prev = GENESIS_HASH

        for r in rows:
            if not r["id"] or not r["timestamp"]:
                return False
            try:
                params_json = r["parameters_json"]
                json.loads(params_json)
            except Exception:
                return False

            actual_prev = r["prev_hash"]
            actual_entry_hash = r["entry_hash"]
            if not actual_prev or not actual_entry_hash:
                return False
            if actual_prev != expected_prev:
                return False

            recomputed_hash = compute_audit_entry_hash(
                prev_hash=actual_prev,
                id=r["id"],
                timestamp=r["timestamp"],
                request_id=r["request_id"],
                principal=r["principal"],
                capability=r["capability"],
                workspace_id=r["workspace_id"],
                action=r["action"],
                policy_decision=r["policy_decision"],
                result=r["result"],
                duration_ms=r["duration_ms"],
                parameters_json=params_json,
            )
            if actual_entry_hash != recomputed_hash:
                return False

            expected_prev = actual_entry_hash

        return True
