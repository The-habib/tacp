"""Unit tests for ApprovalEngine state machine and race condition hardening."""

import threading
from pathlib import Path

import pytest

from tacp.control.approval import (
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REVOKED,
    ApprovalEngine,
)
from tacp.domain.errors import TacpSecurityError
from tacp.infrastructure.database import Database


def test_approval_state_machine_transitions(tmp_path: Path) -> None:
    db = Database(tmp_path / "appr_state.db")
    engine = ApprovalEngine(db)

    # 1. Create ticket -> PENDING
    ticket = engine.create_ticket(
        principal_id="agent-1",
        action_type="workspace.patch",
        workspace_id="ws-1",
        target_path="main.py",
        patch_hash="abc123hash",
    )
    assert ticket.status == STATUS_PENDING

    # 2. Approve ticket -> APPROVED
    approved = engine.approve(ticket.token, approved_by="human_operator")
    assert approved.status == STATUS_APPROVED

    # 3. Cannot approve again (not in PENDING)
    with pytest.raises(TacpSecurityError) as exc:
        engine.approve(ticket.token, approved_by="human_operator")
    assert "Cannot approve ticket" in str(exc.value)

    # 4. Consume ticket -> CONSUMED
    consumed = engine.verify_and_consume(
        token=ticket.token,
        principal_id="agent-1",
        action_type="workspace.patch",
        workspace_id="ws-1",
        target_path="main.py",
        patch_hash="abc123hash",
    )
    assert consumed is True

    # 5. Cannot consume again
    with pytest.raises(TacpSecurityError) as exc:
        engine.verify_and_consume(
            token=ticket.token,
            principal_id="agent-1",
            action_type="workspace.patch",
            workspace_id="ws-1",
            target_path="main.py",
            patch_hash="abc123hash",
        )
    assert "already been consumed" in str(exc.value)

    # 6. Cannot revoke or deny consumed ticket
    with pytest.raises(TacpSecurityError) as exc:
        engine.revoke(ticket.token, reason="test")
    assert "Cannot revoke ticket" in str(exc.value)


def test_concurrent_approve_and_revoke_race(tmp_path: Path) -> None:
    db = Database(tmp_path / "appr_race.db")
    engine = ApprovalEngine(db)

    ticket = engine.create_ticket(
        principal_id="agent-1",
        action_type="workspace.patch",
        workspace_id="ws-1",
        target_path="main.py",
        patch_hash="abc123hash",
    )

    barrier = threading.Barrier(2)
    results: dict[str, str] = {}
    errors: list[Exception] = []

    def try_approve() -> None:
        try:
            barrier.wait()
            engine.approve(ticket.token)
            results["approve"] = "SUCCESS"
        except Exception as exc:
            errors.append(exc)
            results["approve"] = f"FAILED: {exc}"

    def try_revoke() -> None:
        try:
            barrier.wait()
            engine.revoke(ticket.token)
            results["revoke"] = "SUCCESS"
        except Exception as exc:
            errors.append(exc)
            results["revoke"] = f"FAILED: {exc}"

    t1 = threading.Thread(target=try_approve)
    t2 = threading.Thread(target=try_revoke)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # The final ticket state in DB must be valid and consistent
    final_ticket = engine.get_ticket(ticket.token)
    assert final_ticket is not None
    assert final_ticket.status in (STATUS_APPROVED, STATUS_REVOKED)
    # If revoke won or approve won, no unexpected authorization occurs
