import json
from typing import Any, Dict, List

from tacp.domain.audit import AuditEvent
from tacp.infrastructure.database import Database
from tacp.infrastructure.logging import redact_dict


class AuditService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def record_event(self, event: AuditEvent) -> None:
        conn = self.db.connect()
        clean_params = redact_dict(event.parameters_redacted)
        conn.execute(
            """
            INSERT INTO audit_logs (
                id, timestamp, request_id, principal, capability,
                workspace_id, action, policy_decision, result,
                duration_ms, parameters_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                json.dumps(clean_params),
            ),
        )
        conn.commit()

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, request_id, principal, capability,
                   workspace_id, action, policy_decision, result,
                   duration_ms, parameters_json
            FROM audit_logs
            ORDER BY timestamp DESC
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
                }
            )
        return events
