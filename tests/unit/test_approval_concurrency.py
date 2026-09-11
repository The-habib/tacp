"""Concurrency, hashing, and authority tests for ApprovalEngine (Sections 14, 15, 16, 39)."""

import concurrent.futures
import hashlib

import pytest

from tacp.control.approval import (
    STATUS_APPROVED,
    STATUS_CONSUMED,
    ApprovalEngine,
)
from tacp.control.identity import Principal, PrincipalType, TrustTier
from tacp.domain.errors import ErrorCode, TacpSecurityError
from tacp.infrastructure.database import Database


def test_token_hash_stored_in_sqlite_raw_token_never_persisted(test_db: Database) -> None:
    """Invariant: Raw bearer token must not be stored in plaintext in SQLite."""
    engine = ApprovalEngine(test_db)
    ticket = engine.create_ticket(
        principal_id="agent-test",
        action_type="workspace.patch",
        workspace_id="ws-sec",
        target_path="src/safe.py",
        patch_hash="patch_hash_123",
    )

    raw_token = ticket.token
    expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    conn = test_db.connect()
    cur = conn.cursor()
    cur.execute("SELECT id, token, token_hash FROM approvals WHERE id = ?;", (ticket.id,))
    row = cur.fetchone()
    assert row is not None
    db_id, db_token, db_token_hash = row

    assert db_token_hash == expected_hash
    # The raw token MUST NOT appear anywhere in the database row
    assert raw_token not in (db_id, db_token, db_token_hash)
    assert db_token.startswith("tacp_appr_hash:")

    # Retrieving by raw bearer token succeeds via hash matching
    fetched = engine.get_ticket(raw_token)
    assert fetched is not None
    assert fetched.id == ticket.id
    assert fetched.token == raw_token


def test_approver_authority_restrictions(test_db: Database) -> None:
    """Invariant: Agents and restricted principals cannot approve tickets."""
    engine = ApprovalEngine(test_db)
    ticket = engine.create_ticket(
        principal_id="agent-requester",
        action_type="workspace.patch",
        workspace_id="ws-sec",
        target_path="src/safe.py",
        patch_hash="patch_hash_123",
    )

    # 1. Self-approval by an agent MUST be denied
    agent_principal = Principal(
        id="agent-requester",
        principal_type=PrincipalType.AGENT,
        trust_tier=TrustTier.RESTRICTED,
    )
    with pytest.raises(TacpSecurityError) as exc_info:
        engine.approve(ticket.token, approver_principal=agent_principal)
    assert exc_info.value.code == ErrorCode.NOT_AUTHORIZED
    assert "insufficient authority" in exc_info.value.message

    # 2. Approval by a human operator MUST succeed
    operator_principal = Principal(
        id="operator-alice",
        principal_type=PrincipalType.HUMAN,
        trust_tier=TrustTier.PRIVILEGED,
    )
    approved = engine.approve(ticket.token, approver_principal=operator_principal)
    assert approved.status == STATUS_APPROVED
    assert approved.metadata.get("approved_by") == "operator-alice"


def test_concurrent_single_use_consumption_race(test_db: Database) -> None:
    """Race test: 10 concurrent threads racing to consume the same approval ticket."""
    engine = ApprovalEngine(test_db)
    ticket = engine.create_ticket(
        principal_id="agent-race",
        action_type="workspace.patch",
        workspace_id="ws-race",
        target_path="src/race.py",
        patch_hash="race_patch_hash_999",
    )
    engine.approve(ticket.token, approved_by="human_admin")

    num_threads = 10
    successes = 0
    replay_errors = 0
    other_errors = 0

    def attempt_consume(thread_idx: int) -> str:
        try:
            res = engine.verify_and_consume(
                token=ticket.token,
                principal_id="agent-race",
                action_type="workspace.patch",
                workspace_id="ws-race",
                target_path="src/race.py",
                patch_hash="race_patch_hash_999",
            )
            return "SUCCESS" if res else "UNKNOWN"
        except TacpSecurityError as exc:
            if exc.code == ErrorCode.APPROVAL_ALREADY_USED:
                return "ALREADY_USED"
            return f"SECURITY_ERROR_{exc.code.value}"
        except Exception as exc:
            return f"UNEXPECTED_{exc}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(attempt_consume, i) for i in range(num_threads)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    for r in results:
        if r == "SUCCESS":
            successes += 1
        elif r == "ALREADY_USED":
            replay_errors += 1
        else:
            other_errors += 1

    # EXACTLY 1 thread must succeed, and all other 9 must receive APPROVAL_ALREADY_USED
    expected_replays = num_threads - 1
    assert replay_errors == expected_replays, f"Expected {expected_replays}, got {replay_errors}"
    assert other_errors == 0, f"Unexpected errors encountered: {results}"

    # Final DB state verification
    final_ticket = engine.get_ticket(ticket.token)
    assert final_ticket is not None
    assert final_ticket.status == STATUS_CONSUMED
