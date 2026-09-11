"""Tests for Cryptographic Audit Hash Chain and Tamper Evidence (Section 30)."""

from tacp.core.audit_service import GENESIS_HASH, AuditService
from tacp.domain.audit import AuditEvent
from tacp.infrastructure.database import Database


def test_audit_hash_chain_clean_integrity(test_db: Database) -> None:
    service = AuditService(test_db)

    # Empty log is valid
    assert service.verify_integrity() is True

    # Record 5 sequential events
    for i in range(5):
        service.record_event(
            AuditEvent(
                capability=f"cap.{i}",
                action="call",
                policy_decision="ALLOW",
                result="SUCCESS",
                duration_ms=10 + i,
                principal=f"agent-{i}",
                workspace_id=f"ws-{i}",
                parameters_redacted={"idx": i},
            )
        )

    # Chain must pass verification
    assert service.verify_integrity() is True

    # Verify genesis linking
    events = service.get_recent_events(limit=10)
    assert len(events) == 5
    # Oldest event has prev_hash == GENESIS_HASH
    oldest = events[-1]
    assert oldest["prev_hash"] == GENESIS_HASH
    assert oldest["entry_hash"] is not None


def test_audit_hash_chain_detects_modified_record(test_db: Database) -> None:
    service = AuditService(test_db)
    for i in range(3):
        service.record_event(
            AuditEvent(
                capability=f"cap.{i}",
                action="call",
                policy_decision="ALLOW",
                result="SUCCESS",
                duration_ms=10,
                principal="agent-1",
            )
        )

    assert service.verify_integrity() is True

    # Tamper with the middle record's policy_decision directly in DB
    conn = test_db.connect()
    with conn:
        conn.execute("UPDATE audit_logs SET policy_decision = 'DENY' WHERE capability = 'cap.1';")

    # Tamper must be immediately detected
    assert service.verify_integrity() is False


def test_audit_hash_chain_detects_deleted_record(test_db: Database) -> None:
    service = AuditService(test_db)
    for i in range(4):
        service.record_event(
            AuditEvent(
                capability=f"cap.{i}",
                action="call",
                policy_decision="ALLOW",
                result="SUCCESS",
                duration_ms=10,
                principal="agent-1",
            )
        )

    assert service.verify_integrity() is True

    # Delete the second record directly from DB
    conn = test_db.connect()
    with conn:
        conn.execute("DELETE FROM audit_logs WHERE capability = 'cap.1';")

    # Broken chain must be detected
    assert service.verify_integrity() is False


def test_audit_hash_chain_detects_reordered_records(test_db: Database) -> None:
    service = AuditService(test_db)
    for i in range(3):
        service.record_event(
            AuditEvent(
                capability=f"cap.{i}",
                action="call",
                policy_decision="ALLOW",
                result="SUCCESS",
                duration_ms=10,
                principal="agent-1",
            )
        )

    assert service.verify_integrity() is True

    # Swap rowids or timestamps in DB
    conn = test_db.connect()
    with conn:
        cur = conn.cursor()
        cur.execute("SELECT id, rowid FROM audit_logs ORDER BY rowid ASC;")
        rows = cur.fetchall()
        id1 = rows[0]["id"]
        id2 = rows[1]["id"]

        # Swap entry_hashes between row 1 and row 2
        cur.execute("SELECT entry_hash FROM audit_logs WHERE id = ?;", (id1,))
        h1 = cur.fetchone()["entry_hash"]
        cur.execute("SELECT entry_hash FROM audit_logs WHERE id = ?;", (id2,))
        h2 = cur.fetchone()["entry_hash"]

        conn.execute("UPDATE audit_logs SET entry_hash = ? WHERE id = ?;", (h2, id1))
        conn.execute("UPDATE audit_logs SET entry_hash = ? WHERE id = ?;", (h1, id2))

    # Reordering/swapping must fail verification
    assert service.verify_integrity() is False


def test_audit_hash_chain_detects_corrupted_json_payload(test_db: Database) -> None:
    service = AuditService(test_db)
    service.record_event(
        AuditEvent(
            capability="fs.read",
            action="read",
            policy_decision="ALLOW",
            result="SUCCESS",
            duration_ms=5,
        )
    )

    assert service.verify_integrity() is True

    # Tamper parameters_json with invalid JSON
    conn = test_db.connect()
    with conn:
        conn.execute("UPDATE audit_logs SET parameters_json = 'INVALID_JSON{';")

    assert service.verify_integrity() is False
