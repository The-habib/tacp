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
        self._latest_entry_hash: Optional[str] = None

    def invalidate_hash_cache(self) -> None:
        """Invalidate the cached latest audit entry hash."""
        with self._lock:
            self._latest_entry_hash = None

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
                self._latest_entry_hash = entry_hash
            except Exception:
                conn.rollback()
                self._latest_entry_hash = None
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

    def verify_chain_detailed(self) -> Dict[str, Any]:
        """Verify the cryptographic hash chain and return pinpoint diagnostics on tampering."""
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT rowid, id, timestamp, request_id, principal, capability,
                   workspace_id, action, policy_decision, result,
                   duration_ms, parameters_json, prev_hash, entry_hash
            FROM audit_logs
            ORDER BY rowid ASC;
            """
        )
        rows = cursor.fetchall()
        expected_prev = GENESIS_HASH

        for seq, r in enumerate(rows, start=1):
            row_id = r["rowid"]
            entry_id = r["id"]
            if not entry_id or not r["timestamp"]:
                return {
                    "valid": False,
                    "sequence": seq,
                    "rowid": row_id,
                    "entry_id": entry_id,
                    "error": "Missing mandatory ID or timestamp field",
                }
            try:
                params_json = r["parameters_json"]
                json.loads(params_json)
            except Exception as e:
                return {
                    "valid": False,
                    "sequence": seq,
                    "rowid": row_id,
                    "entry_id": entry_id,
                    "error": f"Corrupted parameters_json: {e}",
                }

            actual_prev = r["prev_hash"]
            actual_entry_hash = r["entry_hash"]
            if not actual_prev or not actual_entry_hash:
                return {
                    "valid": False,
                    "sequence": seq,
                    "rowid": row_id,
                    "entry_id": entry_id,
                    "error": "Missing hash pointers in record",
                }
            if actual_prev != expected_prev:
                return {
                    "valid": False,
                    "sequence": seq,
                    "rowid": row_id,
                    "entry_id": entry_id,
                    "error": "Broken previous hash pointer (tampering/deletion detected)",
                    "expected_prev_hash": expected_prev,
                    "actual_prev_hash": actual_prev,
                }

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
                return {
                    "valid": False,
                    "sequence": seq,
                    "rowid": row_id,
                    "entry_id": entry_id,
                    "error": "Mutated row data or invalid entry hash (tampering detected)",
                    "expected_entry_hash": recomputed_hash,
                    "actual_entry_hash": actual_entry_hash,
                }

            expected_prev = actual_entry_hash

        return {
            "valid": True,
            "total_records": len(rows),
            "genesis_hash": GENESIS_HASH,
            "tip_hash": expected_prev,
        }

    def verify_integrity(self) -> bool:
        """Verify the cryptographic hash chain and structural integrity of all audit records."""
        return bool(self.verify_chain_detailed()["valid"])

    def reanchor_chain(self) -> Dict[str, Any]:
        """Cryptographically recompute and repair hash pointers across all historical records."""
        with self._lock:
            conn = self.db.connect()
            conn.execute("BEGIN IMMEDIATE;")
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT rowid, id, timestamp, request_id, principal, capability,
                           workspace_id, action, policy_decision, result,
                           duration_ms, parameters_json
                    FROM audit_logs
                    ORDER BY rowid ASC;
                    """
                )
                rows = cursor.fetchall()
                prev_hash = GENESIS_HASH
                reanchored_count = 0

                for r in rows:
                    entry_hash = compute_audit_entry_hash(
                        prev_hash=prev_hash,
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
                        parameters_json=r["parameters_json"],
                    )
                    conn.execute(
                        "UPDATE audit_logs SET prev_hash = ?, entry_hash = ? WHERE rowid = ?;",
                        (prev_hash, entry_hash, r["rowid"]),
                    )
                    prev_hash = entry_hash
                    reanchored_count += 1

                conn.commit()
                self._latest_entry_hash = prev_hash
                return {
                    "reanchored": True,
                    "total_records": reanchored_count,
                    "tip_hash": prev_hash,
                }
            except Exception:
                conn.rollback()
                self._latest_entry_hash = None
                raise
