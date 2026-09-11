from dataclasses import dataclass
from typing import Optional

from tacp.control.identity import RequestContext
from tacp.domain.errors import ErrorCode, TacpSecurityError
from tacp.domain.workspace import Workspace


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    requires_audit: bool = True


class PolicyEngine:
    ALLOWED_CAPABILITIES = {
        "system.inspect",
        "system.health",
        "system.version",
        "capabilities.list",
        "workspace.list",
        "workspace.inspect",
        "fs.list",
        "fs.stat",
        "fs.read",
        "fs.search",
        "process.list",
        "process.inspect",
        "audit.recent",
    }

    def __init__(self, read_only_enforced: bool = True) -> None:
        self.read_only_enforced = read_only_enforced

    def evaluate_request(
        self,
        context: RequestContext,
        workspace: Optional[Workspace] = None,
    ) -> PolicyDecision:
        cap = context.capability

        # Invariant 1: Check known read-only capabilities (Default Deny)
        if cap not in self.ALLOWED_CAPABILITIES:
            return PolicyDecision(
                allowed=False,
                reason=f"Capability '{cap}' is not recognized or forbidden in TACP 0.1",
            )

        # Invariant 2: Workspace status check
        if workspace is not None:
            if workspace.status != "ACTIVE":
                return PolicyDecision(
                    allowed=False,
                    reason=f"Workspace '{workspace.id}' is not ACTIVE (status: {workspace.status})",
                )

        return PolicyDecision(
            allowed=True,
            reason="Authorized under TACP 0.1 read-only baseline policy",
            requires_audit=True,
        )

    def enforce(
        self,
        context: RequestContext,
        workspace: Optional[Workspace] = None,
    ) -> None:
        decision = self.evaluate_request(context, workspace)
        if not decision.allowed:
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Policy violation: {decision.reason}",
            )

    # Compatibility alias
    check_or_raise = enforce
