from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from tacp.control.identity import PrincipalType, RequestContext, TrustTier
from tacp.domain.errors import (
    ErrorCode,
    TacpApprovalRequiredError,
    TacpSecurityError,
)
from tacp.domain.workspace import Workspace


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    requires_audit: bool = True
    decision_type: str = "ALLOW"

    def is_allowed(self) -> bool:
        return self.allowed

    def is_deny(self) -> bool:
        return not self.allowed and self.decision_type == "DENY"

    def requires_approval(self) -> bool:
        return self.decision_type == "REQUIRE_APPROVAL"


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

    MUTATING_CAPABILITIES = {
        "workspace.patch",
        "workspace.patch_batch",
        "workspace.rollback",
        "workspace.batch_rollback",
    }

    PROTECTED_PATTERNS = {
        ".git",
        ".tacp",
        "tacp.db",
        ".env",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "id_dsa",
    }

    def __init__(
        self,
        read_only_enforced: bool = True,
        mutation_enabled: bool = False,
        batch_mutation_enabled: bool = False,
    ) -> None:
        self.read_only_enforced = read_only_enforced
        self.mutation_enabled = mutation_enabled
        self.batch_mutation_enabled = batch_mutation_enabled

    def _check_target_path(self, target_path: str) -> Optional[PolicyDecision]:
        clean_target = target_path.replace("\\", "/")
        parts = [p for p in clean_target.split("/") if p]
        if ".." in parts:
            return PolicyDecision(
                allowed=False,
                reason="Path traversal detected in target path",
                decision_type="DENY",
            )
        for part in parts:
            if (
                part in self.PROTECTED_PATTERNS
                or part.startswith(".git")
                or part.startswith(".tacp")
            ):
                return PolicyDecision(
                    allowed=False,
                    reason=(f"Access to protected resource '{part}' is denied by Platform Policy"),
                    decision_type="DENY",
                )
        filename = Path(clean_target).name
        if filename.startswith(".env") or "id_rsa" in filename or "id_ed25519" in filename:
            return PolicyDecision(
                allowed=False,
                reason=(f"Access to protected resource '{filename}' is denied by Platform Policy"),
                decision_type="DENY",
            )
        return None

    def evaluate_request(
        self,
        context: RequestContext,
        workspace: Optional[Workspace] = None,
        target_path: Optional[str] = None,
        dry_run: bool = False,
        has_approval: bool = False,
        target_paths: Optional[list[str]] = None,
    ) -> PolicyDecision:
        cap = context.capability

        # Invariant 1: Check known capabilities (Default Deny)
        if cap not in self.ALLOWED_CAPABILITIES and cap not in self.MUTATING_CAPABILITIES:
            return PolicyDecision(
                allowed=False,
                reason=f"Capability '{cap}' is not recognized or forbidden in TACP 0.1",
                decision_type="DENY",
            )

        # Invariant 2: Mutating capability handling
        if cap in self.MUTATING_CAPABILITIES:
            if not self.mutation_enabled:
                return PolicyDecision(
                    allowed=False,
                    reason=(
                        f"Capability '{cap}' is forbidden: "
                        "mutation is disabled in TACP configuration"
                    ),
                    decision_type="DENY",
                )

            if cap == "workspace.patch_batch" and not self.batch_mutation_enabled:
                return PolicyDecision(
                    allowed=False,
                    reason=(
                        f"Capability '{cap}' is forbidden: "
                        "batch mutation is disabled in TACP configuration"
                    ),
                    decision_type="DENY",
                )

            if workspace is None:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Capability '{cap}' requires an active workspace",
                    decision_type="DENY",
                )

            if workspace.status != "ACTIVE":
                return PolicyDecision(
                    allowed=False,
                    reason=f"Workspace '{workspace.id}' is not ACTIVE (status: {workspace.status})",
                    decision_type="DENY",
                )

            # Check single path or multiple paths
            all_targets: list[str] = []
            if target_path is not None:
                all_targets.append(target_path)
            if target_paths is not None:
                all_targets.extend(target_paths)

            for target in all_targets:
                denial = self._check_target_path(target)
                if denial:
                    return denial

            # Special authorization governance for rollback operations
            if cap in ("workspace.rollback", "workspace.batch_rollback"):
                is_elevated_type = context.principal.principal_type in (
                    PrincipalType.HUMAN,
                    PrincipalType.SYSTEM,
                )
                if (
                    context.principal.trust_tier == TrustTier.PRIVILEGED
                    or is_elevated_type
                    or context.principal.role == "operator"
                    or context.principal.id in ("operator", "human_operator")
                ):
                    return PolicyDecision(
                        allowed=True,
                        reason=f"Authorized operator rollback under {cap}",
                        decision_type="ALLOW",
                        requires_audit=True,
                    )
                if has_approval:
                    return PolicyDecision(
                        allowed=True,
                        reason=f"Authorized {cap} execution with valid approval",
                        decision_type="ALLOW",
                        requires_audit=True,
                    )
                return PolicyDecision(
                    allowed=False,
                    reason=f"Execution of '{cap}' by agent requires explicit human approval",
                    decision_type="REQUIRE_APPROVAL",
                    requires_audit=True,
                )

            if dry_run:
                return PolicyDecision(
                    allowed=True,
                    reason="Authorized dry-run evaluation under Workspace Policy",
                    decision_type="ALLOW",
                    requires_audit=True,
                )

            if has_approval:
                return PolicyDecision(
                    allowed=True,
                    reason=f"Authorized mutating {cap} execution with valid approval",
                    decision_type="ALLOW",
                    requires_audit=True,
                )

            return PolicyDecision(
                allowed=False,
                reason=f"Execution of '{cap}' requires explicit human approval",
                decision_type="REQUIRE_APPROVAL",
                requires_audit=True,
            )

        # Invariant 3: Workspace status check for read-only workspace operations
        if workspace is not None:
            if workspace.status != "ACTIVE":
                return PolicyDecision(
                    allowed=False,
                    reason=f"Workspace '{workspace.id}' is not ACTIVE (status: {workspace.status})",
                    decision_type="DENY",
                )

        return PolicyDecision(
            allowed=True,
            reason="Authorized under TACP 0.1 read-only baseline policy",
            decision_type="ALLOW",
            requires_audit=True,
        )

    def enforce(
        self,
        context: RequestContext,
        workspace: Optional[Workspace] = None,
        target_path: Optional[str] = None,
        dry_run: bool = False,
        has_approval: bool = False,
        target_paths: Optional[list[str]] = None,
    ) -> None:
        decision = self.evaluate_request(
            context,
            workspace=workspace,
            target_path=target_path,
            dry_run=dry_run,
            has_approval=has_approval,
            target_paths=target_paths,
        )
        if not decision.allowed:
            if decision.decision_type == "REQUIRE_APPROVAL":
                raise TacpApprovalRequiredError(f"Policy requires approval: {decision.reason}")
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Policy violation: {decision.reason}",
            )

    # Compatibility alias
    check_or_raise = enforce
