"""Unit tests for TACP Phase 6: Risk-Adaptive Governance, Trust Profiles & Leases."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

from tacp.control.approval import ApprovalEngine
from tacp.control.identity import Principal, RequestContext
from tacp.control.lease import LeaseEngine
from tacp.control.policy import PolicyEngine
from tacp.control.risk import RiskEvaluator, RiskLevel
from tacp.core.audit_service import AuditService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.audit import AuditEvent
from tacp.domain.errors import (
    ErrorCode,
    TacpSecurityError,
)
from tacp.infrastructure.database import Database


@pytest.fixture
def temp_env() -> Generator[Dict[str, Any], None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        db_path = root / "tacp_test.db"
        db = Database(db_path)
        ws_service = WorkspaceService(db)
        ws_root = root / "ws"
        ws_root.mkdir()
        ws = ws_service.register_workspace("test-ws", ws_root)
        audit_service = AuditService(db)
        lease_engine = LeaseEngine(db)
        approval_engine = ApprovalEngine(db)
        yield {
            "root": root,
            "db": db,
            "ws_service": ws_service,
            "ws": ws,
            "audit_service": audit_service,
            "lease_engine": lease_engine,
            "approval_engine": approval_engine,
        }
        db.close()


class TestRiskEvaluatorPhase6:
    def test_risk_ladder_mappings(self) -> None:
        assert RiskEvaluator.evaluate("fs.read") == RiskLevel.R0
        assert RiskEvaluator.evaluate("fs.list") == RiskLevel.R0
        assert RiskEvaluator.evaluate("system.inspect") == RiskLevel.R0
        assert RiskEvaluator.evaluate("audit.verify_integrity") == RiskLevel.R0

        assert RiskEvaluator.evaluate("workspace.patch", dry_run=True) == RiskLevel.R1
        assert RiskEvaluator.evaluate("execution.request", dry_run=True) == RiskLevel.R1

        assert RiskEvaluator.evaluate("workspace.patch", dry_run=False) == RiskLevel.R2
        assert RiskEvaluator.evaluate("workspace.patch_batch", dry_run=False) == RiskLevel.R2

        assert RiskEvaluator.evaluate("execution.request", dry_run=False) == RiskLevel.R3

        assert RiskEvaluator.evaluate("emergency_stop") == RiskLevel.R5
        assert RiskEvaluator.evaluate("policy.reconfigure") == RiskLevel.R5


class TestLeaseEngine:
    def test_create_and_get_lease(self, temp_env: Dict[str, Any]) -> None:
        le: LeaseEngine = temp_env["lease_engine"]
        ws = temp_env["ws"]
        lease = le.create_lease(
            principal_id="agent-007",
            workspace_id=ws.id,
            capabilities=["workspace.patch", "workspace.patch_batch"],
            resources=["src/*", "docs/*"],
            risk_ceiling="R2",
            budget=10,
            duration_seconds=1200,
            trust_profile="BALANCED",
        )
        assert lease.lease_id.startswith("lease-")
        assert lease.budget == 10
        assert lease.budget_remaining == 10
        assert lease.is_active() is True
        assert lease.allows_capability("workspace.patch") is True
        assert lease.allows_capability("execution.request") is False
        assert lease.allows_resource("src/main.py") is True
        assert lease.allows_resource("etc/passwd") is False

        fetched = le.get_lease(lease.lease_id)
        assert fetched is not None
        assert fetched.lease_id == lease.lease_id
        assert fetched.principal_id == "agent-007"
        assert fetched.workspace_id == ws.id

    def test_atomic_consumption(self, temp_env: Dict[str, Any]) -> None:
        le: LeaseEngine = temp_env["lease_engine"]
        ws = temp_env["ws"]
        lease = le.create_lease(
            principal_id="agent-1",
            workspace_id=ws.id,
            capabilities=["workspace.patch"],
            budget=2,
            duration_seconds=600,
        )

        assert (
            le.verify_and_consume(
                lease_id=lease.lease_id,
                principal_id="agent-1",
                capability="workspace.patch",
                workspace_id=ws.id,
                risk_level="R2",
                target_path="file.txt",
            )
            is True
        )

        l1 = le.get_lease(lease.lease_id)
        assert l1 is not None and l1.budget_remaining == 1

        assert (
            le.verify_and_consume(
                lease_id=lease.lease_id,
                principal_id="agent-1",
                capability="workspace.patch",
                workspace_id=ws.id,
                risk_level="R2",
                target_path="file2.txt",
            )
            is True
        )

        l2 = le.get_lease(lease.lease_id)
        assert l2 is not None and l2.budget_remaining == 0
        assert l2.is_active() is False

        # 3rd consumption must fail with APPROVAL_EXPIRED or APPROVAL_ALREADY_USED
        with pytest.raises(TacpSecurityError) as exc:
            le.verify_and_consume(
                lease_id=lease.lease_id,
                principal_id="agent-1",
                capability="workspace.patch",
                workspace_id=ws.id,
                risk_level="R2",
            )
        assert exc.value.code in (ErrorCode.APPROVAL_EXPIRED, ErrorCode.APPROVAL_ALREADY_USED)

    def test_revocation(self, temp_env: Dict[str, Any]) -> None:
        le: LeaseEngine = temp_env["lease_engine"]
        ws = temp_env["ws"]
        lease = le.create_lease(
            principal_id="agent-rev",
            workspace_id=ws.id,
            capabilities=["workspace.patch"],
            budget=5,
        )
        assert le.revoke_lease(lease.lease_id) is True
        revoked = le.get_lease(lease.lease_id)
        assert revoked is not None and revoked.revoked is True
        assert revoked.is_active() is False

        with pytest.raises(TacpSecurityError) as exc:
            le.verify_and_consume(
                lease_id=lease.lease_id,
                principal_id="agent-rev",
                capability="workspace.patch",
                workspace_id=ws.id,
                risk_level="R2",
            )
        assert exc.value.code == ErrorCode.NOT_AUTHORIZED

    def test_revoke_all_leases(self, temp_env: Dict[str, Any]) -> None:
        le: LeaseEngine = temp_env["lease_engine"]
        ws = temp_env["ws"]
        le.create_lease("a1", ws.id, ["workspace.patch"])
        le.create_lease("a2", ws.id, ["workspace.patch"])
        count = le.revoke_all_leases(workspace_id=ws.id)
        assert count == 2
        assert len(le.list_leases(workspace_id=ws.id, active_only=True)) == 0


class TestTrustProfilesAndPolicy:
    def test_lockdown_profile_denies_mutation_and_execution(self, temp_env: Dict[str, Any]) -> None:
        le: LeaseEngine = temp_env["lease_engine"]
        ws = temp_env["ws"]
        policy = PolicyEngine(
            mutation_enabled=True,
            execution_enabled=True,
            trust_profile="LOCKDOWN",
            lease_engine=le,
        )

        ctx_read = RequestContext(capability="fs.read", principal=Principal.local_agent("ag"))
        d_read = policy.evaluate_request(ctx_read, workspace=ws)
        assert d_read.allowed is True

        ctx_patch = RequestContext(
            capability="workspace.patch", principal=Principal.local_agent("ag")
        )
        d_patch = policy.evaluate_request(ctx_patch, workspace=ws)
        assert d_patch.allowed is False
        assert d_patch.decision_type == "DENY"

        ctx_exec = RequestContext(
            capability="execution.request", principal=Principal.local_agent("ag")
        )
        d_exec = policy.evaluate_request(ctx_exec, workspace=ws)
        assert d_exec.allowed is False
        assert d_exec.decision_type == "DENY"

    def test_strict_profile_requires_approval_even_with_lease(
        self, temp_env: Dict[str, Any]
    ) -> None:
        le: LeaseEngine = temp_env["lease_engine"]
        ws = temp_env["ws"]
        lease = le.create_lease("ag", ws.id, ["workspace.patch"], budget=5)
        policy = PolicyEngine(
            mutation_enabled=True,
            trust_profile="STRICT",
            lease_engine=le,
        )
        ctx = RequestContext(capability="workspace.patch", principal=Principal.local_agent("ag"))
        dec = policy.evaluate_request(ctx, workspace=ws, lease_id=lease.lease_id)
        assert dec.allowed is False
        assert dec.decision_type == "REQUIRE_APPROVAL"
        assert "STRICT" in dec.reason

    def test_balanced_profile_accepts_valid_lease(self, temp_env: Dict[str, Any]) -> None:
        le: LeaseEngine = temp_env["lease_engine"]
        ws = temp_env["ws"]
        lease = le.create_lease("ag", ws.id, ["workspace.patch"], budget=5)
        policy = PolicyEngine(
            mutation_enabled=True,
            trust_profile="BALANCED",
            lease_engine=le,
        )
        ctx = RequestContext(capability="workspace.patch", principal=Principal.local_agent("ag"))
        dec = policy.evaluate_request(ctx, workspace=ws, lease_id=lease.lease_id)
        assert dec.allowed is True
        assert dec.decision_type == "ALLOW_WITH_LEASE"

    def test_developer_profile_permits_workspace_patch_directly(
        self, temp_env: Dict[str, Any]
    ) -> None:
        ws = temp_env["ws"]
        policy = PolicyEngine(
            mutation_enabled=True,
            execution_enabled=True,
            trust_profile="DEVELOPER",
        )
        ctx_patch = RequestContext(
            capability="workspace.patch", principal=Principal.local_agent("ag")
        )
        dec_patch = policy.evaluate_request(ctx_patch, workspace=ws, target_path="code.py")
        assert dec_patch.allowed is True
        assert "DEVELOPER" in dec_patch.reason

        # Negative Invariant: DEVELOPER profile must NEVER permit execution.request
        # without ticket/lease!
        ctx_exec = RequestContext(
            capability="execution.request", principal=Principal.local_agent("ag")
        )
        dec_exec = policy.evaluate_request(ctx_exec, workspace=ws)
        assert dec_exec.allowed is False
        assert dec_exec.decision_type == "REQUIRE_APPROVAL"


class TestApprovalGrouping:
    def test_create_and_consume_group_ticket(self, temp_env: Dict[str, Any]) -> None:
        ae: ApprovalEngine = temp_env["approval_engine"]
        ws = temp_env["ws"]
        plan_hash = "sha256-abcdef1234567890"

        ticket = ae.create_group_ticket(
            principal_id="agent-grp",
            action_type="workspace.patch_batch",
            workspace_id=ws.id,
            plan_hash=plan_hash,
            metadata={"files_count": 3},
        )
        assert ticket.target_path == "*"
        assert ticket.metadata["is_group"] is True

        ae.approve(ticket.token, approved_by="operator-1")

        # Verify and consume group
        assert (
            ae.verify_and_consume_group(
                token=ticket.token,
                principal_id="agent-grp",
                action_type="workspace.patch_batch",
                workspace_id=ws.id,
                plan_hash=plan_hash,
            )
            is True
        )

        # Replay must fail
        with pytest.raises(TacpSecurityError) as exc:
            ae.verify_and_consume_group(
                token=ticket.token,
                principal_id="agent-grp",
                action_type="workspace.patch_batch",
                workspace_id=ws.id,
                plan_hash=plan_hash,
            )
        assert exc.value.code == ErrorCode.APPROVAL_ALREADY_USED


class TestAuditIntegrityCapability:
    def test_audit_verify_integrity(self, temp_env: Dict[str, Any]) -> None:
        audit_svc: AuditService = temp_env["audit_service"]
        ws = temp_env["ws"]

        # Record 3 events
        for i in range(3):
            audit_svc.record_event(
                AuditEvent(
                    capability="fs.read",
                    action=f"read_{i}",
                    policy_decision="ALLOW",
                    result="SUCCESS",
                    duration_ms=2,
                    principal="test_agent",
                    request_id=f"req-{i}",
                    workspace_id=ws.id,
                    parameters_redacted={"idx": i},
                )
            )

        assert audit_svc.verify_integrity() is True
