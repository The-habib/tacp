"""Unit tests for ApprovalEngine (Category M & H)."""

import pytest

from tacp.control.approval import (
    STATUS_APPROVED,
    STATUS_CONSUMED,
    STATUS_DENIED,
    STATUS_PENDING,
    STATUS_REVOKED,
    ApprovalEngine,
)
from tacp.domain.errors import (
    ErrorCode,
    TacpApprovalRequiredError,
    TacpSecurityError,
)
from tacp.infrastructure.database import Database


@pytest.fixture
def approval_engine(test_db: Database) -> ApprovalEngine:
    return ApprovalEngine(test_db)


def test_create_ticket(approval_engine: ApprovalEngine) -> None:
    ticket = approval_engine.create_ticket(
        principal_id="agent-1",
        action_type="workspace.patch",
        workspace_id="ws-1",
        target_path="src/main.py",
        patch_hash="abc123hash",
        ttl_seconds=300,
    )
    assert ticket.id.startswith("appr-")
    assert ticket.token.startswith("tacp_appr_")
    assert ticket.status == STATUS_PENDING
    assert ticket.principal_id == "agent-1"
    assert ticket.action_type == "workspace.patch"
    assert ticket.workspace_id == "ws-1"
    assert ticket.target_path == "src/main.py"
    assert ticket.patch_hash == "abc123hash"


def test_get_ticket(approval_engine: ApprovalEngine) -> None:
    ticket = approval_engine.create_ticket(
        principal_id="agent-1",
        action_type="workspace.patch",
        workspace_id="ws-1",
        target_path="src/main.py",
        patch_hash="abc123hash",
    )
    fetched = approval_engine.get_ticket(ticket.token)
    assert fetched is not None
    assert fetched.id == ticket.id
    assert fetched.token == ticket.token

    assert approval_engine.get_ticket("nonexistent_token") is None


def test_approve_ticket(approval_engine: ApprovalEngine) -> None:
    ticket = approval_engine.create_ticket(
        principal_id="agent-1",
        action_type="workspace.patch",
        workspace_id="ws-1",
        target_path="src/main.py",
        patch_hash="abc123hash",
    )
    approved = approval_engine.approve(ticket.token, approved_by="ceo")
    assert approved.status == STATUS_APPROVED
    assert approved.metadata.get("approved_by") == "ceo"


def test_deny_ticket(approval_engine: ApprovalEngine) -> None:
    ticket = approval_engine.create_ticket(
        principal_id="agent-1",
        action_type="workspace.patch",
        workspace_id="ws-1",
        target_path="src/main.py",
        patch_hash="abc123hash",
    )
    denied = approval_engine.deny(ticket.token, denied_by="ceo", reason="Too risky")
    assert denied.status == STATUS_DENIED
    assert denied.metadata.get("deny_reason") == "Too risky"


def test_revoke_ticket(approval_engine: ApprovalEngine) -> None:
    ticket = approval_engine.create_ticket(
        principal_id="agent-1",
        action_type="workspace.patch",
        workspace_id="ws-1",
        target_path="src/main.py",
        patch_hash="abc123hash",
    )
    revoked = approval_engine.revoke(ticket.token, reason="Emergency revocation")
    assert revoked.status == STATUS_REVOKED


def test_cannot_approve_non_pending(approval_engine: ApprovalEngine) -> None:
    ticket = approval_engine.create_ticket(
        principal_id="agent-1",
        action_type="workspace.patch",
        workspace_id="ws-1",
        target_path="src/main.py",
        patch_hash="abc123hash",
    )
    approval_engine.deny(ticket.token)
    with pytest.raises(TacpSecurityError):
        approval_engine.approve(ticket.token)


def test_verify_and_consume_success(approval_engine: ApprovalEngine) -> None:
    ticket = approval_engine.create_ticket(
        principal_id="agent-1",
        action_type="workspace.patch",
        workspace_id="ws-1",
        target_path="src/main.py",
        patch_hash="hash999",
    )
    approval_engine.approve(ticket.token)

    consumed = approval_engine.verify_and_consume(
        token=ticket.token,
        principal_id="agent-1",
        action_type="workspace.patch",
        workspace_id="ws-1",
        target_path="src/main.py",
        patch_hash="hash999",
    )
    assert consumed is True

    # Check updated state in DB
    updated = approval_engine.get_ticket(ticket.token)
    assert updated is not None
    assert updated.status == STATUS_CONSUMED
    assert updated.consumed_by == "agent-1"
    assert updated.consumed_at is not None


def test_verify_and_consume_replay_rejected(approval_engine: ApprovalEngine) -> None:
    ticket = approval_engine.create_ticket(
        principal_id="agent-1",
        action_type="workspace.patch",
        workspace_id="ws-1",
        target_path="src/main.py",
        patch_hash="hash999",
    )
    approval_engine.approve(ticket.token)
    approval_engine.verify_and_consume(
        token=ticket.token,
        principal_id="agent-1",
        action_type="workspace.patch",
        workspace_id="ws-1",
        target_path="src/main.py",
        patch_hash="hash999",
    )

    with pytest.raises(TacpSecurityError) as exc_info:
        approval_engine.verify_and_consume(
            token=ticket.token,
            principal_id="agent-1",
            action_type="workspace.patch",
            workspace_id="ws-1",
            target_path="src/main.py",
            patch_hash="hash999",
        )
    assert exc_info.value.code == ErrorCode.APPROVAL_ALREADY_USED


def test_verify_and_consume_expired(approval_engine: ApprovalEngine) -> None:
    ticket = approval_engine.create_ticket(
        principal_id="agent-1",
        action_type="workspace.patch",
        workspace_id="ws-1",
        target_path="src/main.py",
        patch_hash="hash999",
        ttl_seconds=-10,  # Already expired
    )
    # Even if status were APPROVED in DB
    conn = approval_engine.db.connect()
    conn.execute(
        "UPDATE approvals SET status = ? WHERE token = ?;", (STATUS_APPROVED, ticket.token)
    )
    conn.commit()

    with pytest.raises(TacpSecurityError) as exc_info:
        approval_engine.verify_and_consume(
            token=ticket.token,
            principal_id="agent-1",
            action_type="workspace.patch",
            workspace_id="ws-1",
            target_path="src/main.py",
            patch_hash="hash999",
        )
    assert exc_info.value.code == ErrorCode.APPROVAL_EXPIRED


def test_verify_and_consume_unapproved(approval_engine: ApprovalEngine) -> None:
    ticket = approval_engine.create_ticket(
        principal_id="agent-1",
        action_type="workspace.patch",
        workspace_id="ws-1",
        target_path="src/main.py",
        patch_hash="hash999",
    )
    with pytest.raises(TacpApprovalRequiredError):
        approval_engine.verify_and_consume(
            token=ticket.token,
            principal_id="agent-1",
            action_type="workspace.patch",
            workspace_id="ws-1",
            target_path="src/main.py",
            patch_hash="hash999",
        )


def test_verify_and_consume_scope_mismatch(approval_engine: ApprovalEngine) -> None:
    ticket = approval_engine.create_ticket(
        principal_id="agent-1",
        action_type="workspace.patch",
        workspace_id="ws-1",
        target_path="src/main.py",
        patch_hash="hash999",
    )
    approval_engine.approve(ticket.token)

    # Action mismatch
    with pytest.raises(TacpSecurityError) as exc:
        approval_engine.verify_and_consume(
            token=ticket.token,
            principal_id="agent-1",
            action_type="fs.write",
            workspace_id="ws-1",
            target_path="src/main.py",
            patch_hash="hash999",
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED

    # Workspace mismatch
    with pytest.raises(TacpSecurityError) as exc:
        approval_engine.verify_and_consume(
            token=ticket.token,
            principal_id="agent-1",
            action_type="workspace.patch",
            workspace_id="ws-foreign",
            target_path="src/main.py",
            patch_hash="hash999",
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED

    # Target path mismatch
    with pytest.raises(TacpSecurityError) as exc:
        approval_engine.verify_and_consume(
            token=ticket.token,
            principal_id="agent-1",
            action_type="workspace.patch",
            workspace_id="ws-1",
            target_path="src/other.py",
            patch_hash="hash999",
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED

    # Patch hash mismatch
    with pytest.raises(TacpSecurityError) as exc:
        approval_engine.verify_and_consume(
            token=ticket.token,
            principal_id="agent-1",
            action_type="workspace.patch",
            workspace_id="ws-1",
            target_path="src/main.py",
            patch_hash="different_hash",
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED

    # Principal mismatch
    with pytest.raises(TacpSecurityError) as exc:
        approval_engine.verify_and_consume(
            token=ticket.token,
            principal_id="attacker-agent",
            action_type="workspace.patch",
            workspace_id="ws-1",
            target_path="src/main.py",
            patch_hash="hash999",
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED
