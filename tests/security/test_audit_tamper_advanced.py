"""Advanced Tamper Detection Test Suite for TACP Audit Hash Chain."""

import sqlite3

import pytest

from tacp.core.audit_service import GENESIS_HASH, AuditService
from tacp.domain.audit import AuditEvent
from tacp.infrastructure.database import Database


@pytest.fixture
def clean_audit_env(tmp_path):
    db_path = tmp_path / "audit_test.db"
    db = Database(db_path)
    db.connect()
    svc = AuditService(db)

    # Record 10 sequential events
    for i in range(10):
        evt = AuditEvent(
            capability=f"cap_{i}",
            action=f"action_{i}",
            policy_decision="ALLOWED",
            result="SUCCESS",
            duration_ms=i,
            principal="agent_1",
            request_id=f"req_{i}",
        )
        svc.record_event(evt)
    return db, svc, db_path


def test_valid_chain(clean_audit_env):
    db, svc, _ = clean_audit_env
    diag = svc.verify_chain_detailed()
    assert diag["valid"] is True
    assert diag["total_records"] == 10
    assert diag["genesis_hash"] == GENESIS_HASH
    assert diag["tip_hash"] != GENESIS_HASH


def test_tamper_detect_data_mutation(clean_audit_env):
    db, svc, db_path = clean_audit_env
    # Mutate record 5: change policy_decision from ALLOWED to DENIED
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE audit_logs SET policy_decision = 'DENIED' WHERE rowid = 5;")
    conn.commit()
    conn.close()

    diag = svc.verify_chain_detailed()
    assert diag["valid"] is False
    assert diag["sequence"] == 5
    assert diag["rowid"] == 5
    assert "Mutated row data" in diag["error"]


def test_tamper_detect_record_deletion(clean_audit_env):
    db, svc, db_path = clean_audit_env
    # Delete record 4
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM audit_logs WHERE rowid = 4;")
    conn.commit()
    conn.close()

    diag = svc.verify_chain_detailed()
    assert diag["valid"] is False
    assert diag["sequence"] == 4
    assert "Broken previous hash pointer" in diag["error"]


def test_tamper_detect_rogue_insertion(clean_audit_env):
    db, svc, db_path = clean_audit_env
    # Insert rogue record between 3 and 4 with fake hash
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO audit_logs (id, timestamp, request_id, principal, capability, action, policy_decision, result, duration_ms, parameters_json, prev_hash, entry_hash)
        VALUES ('rogue-id', '2026-09-26T00:00:00Z', 'req-x', 'attacker', 'cap_x', 'action_x', 'ALLOWED', 'SUCCESS', 1, '{}', 'deadbeef', 'cafebabe');
        """
    )
    conn.commit()
    conn.close()

    diag = svc.verify_chain_detailed()
    assert diag["valid"] is False
