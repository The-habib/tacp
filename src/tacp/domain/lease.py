"""Domain entities for Bounded Capability Leases."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from tacp.control.risk import RiskLevel

RISK_ORDER = {
    RiskLevel.R0.value: 0,
    RiskLevel.R1.value: 1,
    RiskLevel.R2.value: 2,
    RiskLevel.R3.value: 3,
    RiskLevel.R4.value: 4,
    RiskLevel.R5.value: 5,
}


@dataclass(frozen=True)
class CapabilityLease:
    """Immutable representation of an authorized capability lease."""

    id: str
    lease_id: str
    principal_id: str
    workspace_id: str
    capabilities: Tuple[str, ...]
    resources: Tuple[str, ...]
    risk_ceiling: str = RiskLevel.R2.value
    budget: int = 1
    budget_remaining: int = 1
    issued_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    trust_profile: str = "BALANCED"
    policy_version: int = 1
    session_id: Optional[str] = None
    revoked: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        """Check if lease is unrevoked, has remaining budget, and is within time window."""
        if self.revoked:
            return False
        if self.budget_remaining <= 0:
            return False
        try:
            exp = datetime.fromisoformat(self.expires_at)
            now = datetime.now(timezone.utc)
            return now < exp
        except (ValueError, TypeError):
            return False

    def allows_capability(self, capability: str) -> bool:
        """Check if capability is in lease allowlist."""
        return capability in self.capabilities

    def allows_risk(self, risk_level: str) -> bool:
        """Check if requested risk level does not exceed risk ceiling."""
        req_order = RISK_ORDER.get(risk_level, 99)
        ceil_order = RISK_ORDER.get(self.risk_ceiling, 0)
        return req_order <= ceil_order

    def allows_resource(self, target_path: Optional[str]) -> bool:
        """Check if target path matches resources patterns if specified."""
        if not self.resources:
            return True
        if not target_path:
            return True
        clean = target_path.strip().lstrip("./")
        for pat in self.resources:
            clean_pat = pat.strip().lstrip("./")
            if fnmatch.fnmatch(clean, clean_pat):
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert lease to dictionary representation."""
        return {
            "id": self.id,
            "lease_id": self.lease_id,
            "principal_id": self.principal_id,
            "workspace_id": self.workspace_id,
            "capabilities": list(self.capabilities),
            "resources": list(self.resources),
            "risk_ceiling": self.risk_ceiling,
            "budget": self.budget,
            "budget_remaining": self.budget_remaining,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "trust_profile": self.trust_profile,
            "policy_version": self.policy_version,
            "session_id": self.session_id,
            "revoked": self.revoked,
            "active": self.is_active(),
            "metadata": self.metadata,
        }
