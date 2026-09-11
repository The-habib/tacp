import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class AuditEvent:
    capability: str
    action: str
    policy_decision: str
    result: str
    duration_ms: int
    principal: str = "anonymous"
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: Optional[str] = None
    parameters_redacted: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "request_id": self.request_id,
            "principal": self.principal,
            "capability": self.capability,
            "workspace_id": self.workspace_id,
            "action": self.action,
            "policy_decision": self.policy_decision,
            "result": self.result,
            "duration_ms": self.duration_ms,
            "parameters": self.parameters_redacted,
        }
