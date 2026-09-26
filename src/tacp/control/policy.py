from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from tacp.control.identity import Authority, PrincipalType, RequestContext, TrustTier
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
    matched_rule: str = "default"
    risk_level: str = "CONTROLLED"
    required_approval: bool = False
    required_authority: Optional[str] = None
    network_state: str = "NETWORK_UNENFORCED"

    def is_allowed(self) -> bool:
        return self.allowed

    def is_deny(self) -> bool:
        return not self.allowed and self.decision_type == "DENY"

    def requires_approval(self) -> bool:
        return self.decision_type == "REQUIRE_APPROVAL" or self.required_approval

    def explanation(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "decision": self.decision_type,
            "reason": self.reason,
            "matched_rule": self.matched_rule,
            "risk_level": self.risk_level,
            "required_approval": self.requires_approval(),
            "required_authority": self.required_authority,
            "network_state": self.network_state,
        }


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
        "audit.verify_integrity",
    }

    MUTATING_CAPABILITIES = {
        "workspace.patch",
        "workspace.patch_batch",
        "workspace.rollback",
        "workspace.batch_rollback",
    }

    EXECUTION_CAPABILITIES = {
        "execution.request",
        "execution.inspect",
        "execution.list",
        "execution.cancel",
    }

    DEVICE_MUTATING_CAPABILITIES = {
        "shell.exec",
        "process.kill",
        "process.signal",
        "package.install",
        "package.uninstall",
        "app.launch",
        "clipboard.set",
        "input.tap",
        "input.key",
        "notifications.post",
        "filesystem.write",
        "filesystem.delete",
        "filesystem.append",
        "filesystem.copy",
        "filesystem.move",
        "filesystem.mkdir",
        "filesystem.unzip",
        "filesystem.zip",
        "automation.create",
        "automation.start",
        "tasks.cancel",
        "tts.speak",
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
        execution_enabled: bool = False,
        network_enabled: bool = False,
        trust_profile: str = "BALANCED",
        lease_engine: Optional[Any] = None,
        remote_enabled: bool = False,
        remote_read_only: bool = False,
        remote_mutation_enabled: bool = False,
        remote_execution_enabled: bool = False,
        device_control_enabled: bool = False,
    ) -> None:
        self.read_only_enforced = read_only_enforced
        self.mutation_enabled = mutation_enabled
        self.batch_mutation_enabled = batch_mutation_enabled
        self.execution_enabled = execution_enabled
        self.network_enabled = network_enabled
        self.trust_profile = trust_profile.upper() if trust_profile else "BALANCED"
        self.lease_engine = lease_engine
        self.remote_enabled = remote_enabled
        self.remote_read_only = remote_read_only or (self.trust_profile == "REMOTE_READ_ONLY")
        self.remote_mutation_enabled = remote_mutation_enabled
        self.remote_execution_enabled = remote_execution_enabled
        self.device_control_enabled = device_control_enabled

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
        lease_id: Optional[str] = None,
    ) -> PolicyDecision:
        cap = context.capability

        is_device_cap = self.device_control_enabled and (
            any(cap.startswith(ns) for ns in (
                "shell.", "device.", "filesystem.", "storage.",
                "package.", "app.", "network.", "wifi.", "camera.", "microphone.",
                "audio.", "tts.", "location.", "sensors.", "clipboard.",
                "notifications.", "screen.", "input.", "settings.", "logs.",
                "tasks.", "automation.", "diagnostics."
            )) or cap in ("process.kill", "process.signal")
        )

        # Invariant 1: Check known capabilities (Default Deny)
        if (
            cap not in self.ALLOWED_CAPABILITIES
            and cap not in self.MUTATING_CAPABILITIES
            and cap not in self.EXECUTION_CAPABILITIES
            and not is_device_cap
        ):
            return PolicyDecision(
                allowed=False,
                reason=f"Capability '{cap}' is not recognized or forbidden in TACP",
                decision_type="DENY",
            )

        # Invariant 1b: Trust Profile LOCKDOWN strictly forbids all mutation and execution
        if self.trust_profile == "LOCKDOWN":
            if cap in self.MUTATING_CAPABILITIES or cap in self.EXECUTION_CAPABILITIES or (is_device_cap and cap in self.DEVICE_MUTATING_CAPABILITIES):
                return PolicyDecision(
                    allowed=False,
                    reason=(
                        "Mutations and executions are strictly prohibited in LOCKDOWN trust profile"
                    ),
                    decision_type="DENY",
                    risk_level="R0",
                )

        # Invariant 1c: Trust Profile REMOTE_READ_ONLY strictly forbids mutation and execution
        if self.trust_profile == "REMOTE_READ_ONLY":
            if (
                cap in self.MUTATING_CAPABILITIES
                or cap in self.EXECUTION_CAPABILITIES
                or cap == "audit.verify_integrity"
                or (is_device_cap and cap in self.DEVICE_MUTATING_CAPABILITIES)
            ):
                return PolicyDecision(
                    allowed=False,
                    reason=(
                        "Operations beyond R0 observation are strictly prohibited "
                        "in REMOTE_READ_ONLY trust profile"
                    ),
                    decision_type="DENY",
                    risk_level="R0",
                )

        # Invariant 1d: Remote AI Principal Governance
        if context.principal.principal_type == PrincipalType.REMOTE_AI:
            if not self.remote_enabled:
                return PolicyDecision(
                    allowed=False,
                    reason="Remote access is disabled in TACP configuration",
                    decision_type="DENY",
                    risk_level="R0",
                )
            if self.remote_read_only or self.trust_profile == "REMOTE_READ_ONLY":
                if (
                    cap in self.MUTATING_CAPABILITIES
                    or cap in self.EXECUTION_CAPABILITIES
                    or cap == "audit.verify_integrity"
                    or (is_device_cap and cap in self.DEVICE_MUTATING_CAPABILITIES)
                ):
                    return PolicyDecision(
                        allowed=False,
                        reason=(
                            "Mutations and executions are strictly prohibited "
                            "for remote agents in read-only mode"
                        ),
                        decision_type="DENY",
                        risk_level="R0",
                    )
            if cap in self.MUTATING_CAPABILITIES and not self.remote_mutation_enabled:
                return PolicyDecision(
                    allowed=False,
                    reason="Remote workspace mutation is disabled in TACP policy",
                    decision_type="DENY",
                    risk_level="R0",
                )
            if cap in self.EXECUTION_CAPABILITIES and not self.remote_execution_enabled:
                return PolicyDecision(
                    allowed=False,
                    reason="Remote process execution is disabled in TACP policy",
                    decision_type="DENY",
                    risk_level="R0",
                )

        # Device Capabilities Governance
        if is_device_cap:
            if cap in self.DEVICE_MUTATING_CAPABILITIES:
                if self.read_only_enforced:
                    return PolicyDecision(
                        allowed=False,
                        reason=f"Mutating device capability '{cap}' is prohibited when read-only enforcement is active",
                        decision_type="DENY",
                        risk_level="R1",
                    )
                if cap == "shell.exec" and not self.execution_enabled:
                    return PolicyDecision(
                        allowed=False,
                        reason="Shell execution is disabled in TACP policy",
                        decision_type="DENY",
                        risk_level="R1",
                    )
            return PolicyDecision(
                allowed=True,
                reason=f"Device capability '{cap}' authorized under trust profile {self.trust_profile}",
                decision_type="ALLOW",
                risk_level="R0" if cap not in self.DEVICE_MUTATING_CAPABILITIES else "R1",
            )

        # Lease Evaluation Helper
        has_lease = False
        lease_rejection_reason: Optional[str] = None
        if lease_id:
            if not self.lease_engine:
                lease_rejection_reason = "No lease engine configured"
            elif self.trust_profile in ("STRICT", "REMOTE_READ_ONLY"):
                lease_rejection_reason = (
                    f"Trust profile {self.trust_profile} does not permit capability leases"
                )
            else:
                lease = self.lease_engine.get_lease(lease_id)
                if not lease:
                    lease_rejection_reason = f"Capability lease '{lease_id}' not found"
                elif lease.revoked:
                    lease_rejection_reason = f"Capability lease '{lease_id}' is revoked"
                elif not lease.is_active():
                    lease_rejection_reason = (
                        f"Capability lease '{lease_id}' is expired or budget exhausted"
                    )
                elif lease.principal_id != context.principal.id:
                    lease_rejection_reason = (
                        f"Lease principal mismatch: expected '{lease.principal_id}', "
                        f"got '{context.principal.id}'"
                    )
                elif workspace is not None and lease.workspace_id != workspace.id:
                    lease_rejection_reason = (
                        f"Lease workspace mismatch: expected '{lease.workspace_id}', "
                        f"got '{workspace.id}'"
                    )
                elif not lease.allows_capability(cap):
                    lease_rejection_reason = (
                        f"Capability '{cap}' is not permitted under lease '{lease_id}'"
                    )
                else:
                    lease_targets: list[str] = []
                    if target_path is not None:
                        lease_targets.append(target_path)
                    if target_paths is not None:
                        lease_targets.extend(target_paths)
                    if not all(lease.allows_resource(t) for t in lease_targets):
                        lease_rejection_reason = f"Target resource outside lease '{lease_id}' scope"
                    else:
                        req_risk = "R3" if cap in self.EXECUTION_CAPABILITIES else "R2"
                        if not lease.allows_risk(req_risk):
                            lease_rejection_reason = (
                                f"Risk level '{req_risk}' exceeds lease risk ceiling "
                                f"'{lease.risk_ceiling}'"
                            )
                        else:
                            has_lease = True

        # Invariant 2: Execution capability handling
        if cap in self.EXECUTION_CAPABILITIES:
            if not self.execution_enabled:
                return PolicyDecision(
                    allowed=False,
                    reason=(
                        f"Capability '{cap}' is forbidden: "
                        "command execution is disabled in TACP configuration"
                    ),
                    decision_type="DENY",
                )

            if workspace is None and cap in ("execution.request", "execution.cancel"):
                return PolicyDecision(
                    allowed=False,
                    reason=f"Capability '{cap}' requires an active workspace",
                    decision_type="DENY",
                )

            if workspace is not None and workspace.status != "ACTIVE":
                return PolicyDecision(
                    allowed=False,
                    reason=f"Workspace '{workspace.id}' is not ACTIVE (status: {workspace.status})",
                    decision_type="DENY",
                )

            if cap in ("execution.list", "execution.inspect"):
                return PolicyDecision(
                    allowed=True,
                    reason=f"Authorized read-only execution query under {cap}",
                    decision_type="ALLOW",
                    requires_audit=True,
                    risk_level="R0",
                )

            if cap == "execution.cancel":
                is_operator = (
                    context.principal.trust_tier == TrustTier.PRIVILEGED
                    and context.principal.principal_type != PrincipalType.AGENT
                )
                if is_operator or has_approval:
                    return PolicyDecision(
                        allowed=True,
                        reason="Authorized execution cancellation",
                        decision_type="ALLOW",
                        requires_audit=True,
                    )
                return PolicyDecision(
                    allowed=False,
                    reason="Execution cancellation requires operator privilege or approval",
                    decision_type="REQUIRE_APPROVAL",
                    requires_audit=True,
                )

            if cap == "execution.request":
                if dry_run:
                    return PolicyDecision(
                        allowed=True,
                        reason="Authorized dry-run evaluation under Execution Policy",
                        decision_type="ALLOW",
                        requires_audit=True,
                        risk_level="R1",
                    )

                if has_approval:
                    return PolicyDecision(
                        allowed=True,
                        reason="Authorized execution request with valid approval",
                        decision_type="ALLOW",
                        requires_audit=True,
                        risk_level="R3",
                    )

                if has_lease:
                    return PolicyDecision(
                        allowed=True,
                        reason=f"Authorized execution request under capability lease '{lease_id}'",
                        decision_type="ALLOW_WITH_LEASE",
                        requires_audit=True,
                        risk_level="R3",
                    )

                return PolicyDecision(
                    allowed=False,
                    reason=lease_rejection_reason
                    or "Execution of command requires explicit human approval",
                    decision_type="REQUIRE_APPROVAL",
                    requires_audit=True,
                    risk_level="R3",
                )

        # Invariant 3: Mutating capability handling
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
                is_agent = context.principal.principal_type == PrincipalType.AGENT
                is_privileged = (
                    context.principal.trust_tier == TrustTier.PRIVILEGED and not is_agent
                )
                is_elevated_type = context.principal.principal_type in (
                    PrincipalType.HUMAN,
                    PrincipalType.SYSTEM,
                )
                has_rollback_auth = context.principal.has_authority(Authority.OPERATOR_ROLLBACK)
                if is_privileged or is_elevated_type or has_rollback_auth:
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
                    risk_level="R1",
                )

            if has_approval:
                return PolicyDecision(
                    allowed=True,
                    reason=f"Authorized mutating {cap} execution with valid approval",
                    decision_type="ALLOW",
                    requires_audit=True,
                    risk_level="R2",
                )

            if has_lease:
                return PolicyDecision(
                    allowed=True,
                    reason=(
                        f"Authorized mutating {cap} execution under capability lease '{lease_id}'"
                    ),
                    decision_type="ALLOW_WITH_LEASE",
                    requires_audit=True,
                    risk_level="R2",
                )

            if self.trust_profile == "DEVELOPER" and cap in (
                "workspace.patch",
                "workspace.patch_batch",
            ):
                return PolicyDecision(
                    allowed=True,
                    reason=f"Authorized mutating {cap} execution under DEVELOPER trust profile",
                    decision_type="ALLOW",
                    requires_audit=True,
                    risk_level="R2",
                )

            return PolicyDecision(
                allowed=False,
                reason=lease_rejection_reason
                or f"Execution of '{cap}' requires explicit human approval",
                decision_type="REQUIRE_APPROVAL",
                requires_audit=True,
                risk_level="R2",
            )

        # Invariant 4: Workspace status check for read-only workspace operations
        if workspace is not None:
            if workspace.status != "ACTIVE":
                return PolicyDecision(
                    allowed=False,
                    reason=f"Workspace '{workspace.id}' is not ACTIVE (status: {workspace.status})",
                    decision_type="DENY",
                )

        return PolicyDecision(
            allowed=True,
            reason="Authorized under TACP read-only baseline policy",
            decision_type="ALLOW",
            requires_audit=True,
            risk_level="R0",
        )

    def enforce(
        self,
        context: RequestContext,
        workspace: Optional[Workspace] = None,
        target_path: Optional[str] = None,
        dry_run: bool = False,
        has_approval: bool = False,
        target_paths: Optional[list[str]] = None,
        lease_id: Optional[str] = None,
    ) -> None:
        decision = self.evaluate_request(
            context,
            workspace=workspace,
            target_path=target_path,
            dry_run=dry_run,
            has_approval=has_approval,
            target_paths=target_paths,
            lease_id=lease_id,
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
