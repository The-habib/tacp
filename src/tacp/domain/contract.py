"""Domain entities for execution contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ExecutionContract:
    contract_id: str
    principal_id: str
    capability: str
    target_resource: str
    risk_level: str = "R2"
    status: str = "ACTIVE"
    request_id: str = ""
    trace_id: str = ""
    workspace_id: str = ""
    policy_decision: str = "ALLOW"
    approval_id: Optional[str] = None
    checksum_before: Optional[str] = None
    timeout_seconds: int = 30
    parameters: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "principal_id": self.principal_id,
            "capability": self.capability,
            "target_resource": self.target_resource,
            "risk_level": self.risk_level,
            "status": self.status,
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "workspace_id": self.workspace_id,
            "policy_decision": self.policy_decision,
            "approval_id": self.approval_id,
            "checksum_before": self.checksum_before,
            "timeout_seconds": self.timeout_seconds,
            "parameters": self.parameters,
            "created_at": self.created_at,
        }
