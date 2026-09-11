"""Sabotage and Fault-Injection Test Suite for TACP Phase 6."""

from __future__ import annotations

import concurrent.futures
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

from tacp.control.approval import ApprovalEngine
from tacp.control.identity import Principal, RequestContext
from tacp.control.lease import LeaseEngine
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.audit import AuditEvent
from tacp.domain.errors import ErrorCode, TacpSecurityError
from tacp.infrastructure.database import Database


@pytest.fixture
def sabotage_env() -> Generator[Dict[str, Any], None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        db_path = root / "tacp_sabotage.db"
        db = Database(db_path)
        ws_svc = WorkspaceService(db)
        ws_root = root / "ws"
        ws_root.mkdir()
        ws = ws_svc.register_workspace("sabotage-ws", ws_root)
        audit_svc = AuditService(db)
        lease_eng = LeaseEngine(db)
        appr_eng = ApprovalEngine(db)

        yield {
            "root": root,
            "db": db,
            "ws": ws,
            "ws_svc": ws_svc,
            "audit_svc": audit_svc,
            "lease_eng": lease_eng,
            "appr_eng": appr_eng,
        }
        db.close()


def test_sabotage_s1_concurrent_lease_consumption_race(sabotage_env: Dict[str, Any]) -> None:
    """S1: 20 concurrent threads race to consume a lease with budget 5."""
    le: LeaseEngine = sabotage_env["lease_eng"]
    ws = sabotage_env["ws"]
    budget = 5
    lease = le.create_lease(
        principal_id="agent-race",
        workspace_id=ws.id,
        capabilities=["workspace.patch"],
        budget=budget,
    )

    success_count = 0
    failure_count = 0

    def attempt_consume() -> bool:
        try:
            return le.verify_and_consume(
                lease_id=lease.lease_id,
                principal_id="agent-race",
                capability="workspace.patch",
                workspace_id=ws.id,
                risk_level="R2",
            )
        except TacpSecurityError:
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(attempt_consume) for _ in range(25)]
        for f in concurrent.futures.as_completed(futures):
            if f.result():
                success_count += 1
            else:
                failure_count += 1

    assert success_count == budget
    assert failure_count == 20
    final_lease = le.get_lease(lease.lease_id)
    assert final_lease is not None
    assert final_lease.budget_remaining == 0


def test_sabotage_s2_lease_id_token_forgery(sabotage_env: Dict[str, Any]) -> None:
    """S2: Attempt to supply forged or fabricated lease IDs."""
    le: LeaseEngine = sabotage_env["lease_eng"]
    ws = sabotage_env["ws"]
    forged_id = "lease-forged000000"

    with pytest.raises(TacpSecurityError) as exc:
        le.verify_and_consume(
            lease_id=forged_id,
            principal_id="agent-attacker",
            capability="workspace.patch",
            workspace_id=ws.id,
            risk_level="R2",
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED
    assert "not found" in str(exc.value).lower()


def test_sabotage_s3_audit_hash_chain_tamper_detection(sabotage_env: Dict[str, Any]) -> None:
    """S3: Cryptographic detection of direct database tampering in audit_logs."""
    audit_svc: AuditService = sabotage_env["audit_svc"]
    ws = sabotage_env["ws"]
    db = sabotage_env["db"]

    for i in range(5):
        audit_svc.record_event(
            AuditEvent(
                capability="system.inspect",
                action="inspect",
                policy_decision="ALLOW",
                result="SUCCESS",
                duration_ms=1,
                principal="agent-1",
                request_id=f"req-{i}",
                workspace_id=ws.id,
                parameters_redacted={"idx": i},
            )
        )

    assert audit_svc.verify_integrity() is True

    # Tamper with row 2
    conn = db.connect()
    with conn:
        conn.execute("UPDATE audit_logs SET result = 'FORGED_SUCCESS' WHERE rowid = 2;")

    assert audit_svc.verify_integrity() is False


def test_sabotage_s4_replay_of_consumed_group_approval(sabotage_env: Dict[str, Any]) -> None:
    """S4: Attempt to replay an already-consumed group approval ticket."""
    appr_eng: ApprovalEngine = sabotage_env["appr_eng"]
    ws = sabotage_env["ws"]
    plan_hash = "sha256-1122334455667788"

    ticket = appr_eng.create_group_ticket(
        principal_id="agent-1",
        action_type="workspace.patch_batch",
        workspace_id=ws.id,
        plan_hash=plan_hash,
    )
    appr_eng.approve(ticket.token)

    # First consumption succeeds
    assert (
        appr_eng.verify_and_consume_group(
            token=ticket.token,
            principal_id="agent-1",
            action_type="workspace.patch_batch",
            workspace_id=ws.id,
            plan_hash=plan_hash,
        )
        is True
    )

    # Replay consumption fails
    with pytest.raises(TacpSecurityError) as exc:
        appr_eng.verify_and_consume_group(
            token=ticket.token,
            principal_id="agent-1",
            action_type="workspace.patch_batch",
            workspace_id=ws.id,
            plan_hash=plan_hash,
        )
    assert exc.value.code == ErrorCode.APPROVAL_ALREADY_USED


def test_sabotage_s5_plan_hash_mismatch_sabotage(sabotage_env: Dict[str, Any]) -> None:
    """S5: Attempt to use approved ticket with an altered plan hash (payload tampering)."""
    appr_eng: ApprovalEngine = sabotage_env["appr_eng"]
    ws = sabotage_env["ws"]
    orig_hash = "sha256-originalplan"
    tampered_hash = "sha256-tamperedplan"

    ticket = appr_eng.create_group_ticket(
        principal_id="agent-1",
        action_type="workspace.patch_batch",
        workspace_id=ws.id,
        plan_hash=orig_hash,
    )
    appr_eng.approve(ticket.token)

    with pytest.raises(TacpSecurityError) as exc:
        appr_eng.verify_and_consume_group(
            token=ticket.token,
            principal_id="agent-1",
            action_type="workspace.patch_batch",
            workspace_id=ws.id,
            plan_hash=tampered_hash,
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED
    assert "patch hash mismatch" in str(exc.value).lower()


def test_sabotage_s6_risk_ceiling_tampering_rejection(sabotage_env: Dict[str, Any]) -> None:
    """S6: Attempt to execute R3 command under R2 ceiling lease."""
    le: LeaseEngine = sabotage_env["lease_eng"]
    ws = sabotage_env["ws"]
    lease = le.create_lease(
        principal_id="agent-1",
        workspace_id=ws.id,
        capabilities=["execution.request"],
        risk_ceiling="R2",  # ceiling capped at R2
        budget=5,
    )

    with pytest.raises(TacpSecurityError) as exc:
        le.verify_and_consume(
            lease_id=lease.lease_id,
            principal_id="agent-1",
            capability="execution.request",
            workspace_id=ws.id,
            risk_level="R3",
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED
    assert "exceeds lease risk ceiling" in str(exc.value).lower()


def test_sabotage_s7_revocation_during_flight(sabotage_env: Dict[str, Any]) -> None:
    """S7: Revoke lease while active; subsequent use is denied immediately."""
    le: LeaseEngine = sabotage_env["lease_eng"]
    ws = sabotage_env["ws"]
    lease = le.create_lease(
        principal_id="agent-inflight",
        workspace_id=ws.id,
        capabilities=["workspace.patch"],
        budget=10,
    )

    # First call succeeds
    assert (
        le.verify_and_consume(
            lease_id=lease.lease_id,
            principal_id="agent-inflight",
            capability="workspace.patch",
            workspace_id=ws.id,
            risk_level="R2",
        )
        is True
    )

    # Mid-operation revocation
    le.revoke_lease(lease.lease_id, reason="Operator emergency halt")

    with pytest.raises(TacpSecurityError) as exc:
        le.verify_and_consume(
            lease_id=lease.lease_id,
            principal_id="agent-inflight",
            capability="workspace.patch",
            workspace_id=ws.id,
            risk_level="R2",
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED
    assert "revoked" in str(exc.value).lower()


def test_sabotage_s8_expiration_time_warp(sabotage_env: Dict[str, Any]) -> None:
    """S8: Artificially warp timestamp past expires_at; verify rejection."""
    le: LeaseEngine = sabotage_env["lease_eng"]
    ws = sabotage_env["ws"]
    db = sabotage_env["db"]

    lease = le.create_lease(
        principal_id="agent-time",
        workspace_id=ws.id,
        capabilities=["workspace.patch"],
        budget=5,
        duration_seconds=300,
    )

    # Warp expires_at into yesterday
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    conn = db.connect()
    with conn:
        conn.execute(
            "UPDATE leases SET expires_at = ? WHERE lease_id = ?", (yesterday, lease.lease_id)
        )

    with pytest.raises(TacpSecurityError) as exc:
        le.verify_and_consume(
            lease_id=lease.lease_id,
            principal_id="agent-time",
            capability="workspace.patch",
            workspace_id=ws.id,
            risk_level="R2",
        )
    assert exc.value.code == ErrorCode.APPROVAL_EXPIRED


def test_sabotage_s9_workspace_status_tampering(sabotage_env: Dict[str, Any]) -> None:
    """S9: Suspending workspace causes immediate cache invalidation and denial."""
    ws_svc: WorkspaceService = sabotage_env["ws_svc"]
    ws = sabotage_env["ws"]
    policy = PolicyEngine(mutation_enabled=True)

    ctx = RequestContext(capability="workspace.patch", principal=Principal.local_agent("agent-1"))
    # Initial active check
    assert ws_svc.get_workspace(ws.id).status == "ACTIVE"

    # Suspend workspace
    conn = sabotage_env["db"].connect()
    with conn:
        conn.execute("UPDATE workspaces SET status = 'SUSPENDED' WHERE id = ?", (ws.id,))

    suspended_ws = ws_svc.get_workspace(ws.id)
    assert suspended_ws.status == "SUSPENDED"

    dec = policy.evaluate_request(ctx, workspace=suspended_ws, target_path="test.py")
    assert dec.allowed is False
    assert dec.decision_type == "DENY"
    assert "SUSPENDED" in dec.reason


def test_sabotage_s10_lockdown_override_attempt(sabotage_env: Dict[str, Any]) -> None:
    """S10: In LOCKDOWN mode, neither valid approvals nor active leases can permit mutation."""
    le: LeaseEngine = sabotage_env["lease_eng"]
    appr_eng: ApprovalEngine = sabotage_env["appr_eng"]
    ws = sabotage_env["ws"]

    lease = le.create_lease("agent-1", ws.id, ["workspace.patch"])
    ticket = appr_eng.create_ticket("agent-1", "workspace.patch", ws.id, "file.txt", "hash")
    appr_eng.approve(ticket.token)

    lockdown_policy = PolicyEngine(
        mutation_enabled=True,
        execution_enabled=True,
        trust_profile="LOCKDOWN",
        lease_engine=le,
    )

    ctx = RequestContext(capability="workspace.patch", principal=Principal.local_agent("agent-1"))

    # Attempt with lease
    dec_lease = lockdown_policy.evaluate_request(ctx, workspace=ws, lease_id=lease.lease_id)
    assert dec_lease.allowed is False
    assert dec_lease.decision_type == "DENY"
    assert "LOCKDOWN" in dec_lease.reason

    # Attempt with approval
    dec_appr = lockdown_policy.evaluate_request(ctx, workspace=ws, has_approval=True)
    assert dec_appr.allowed is False
    assert dec_appr.decision_type == "DENY"
    assert "LOCKDOWN" in dec_appr.reason
