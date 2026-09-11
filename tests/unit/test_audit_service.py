"""Tests for Audit Logging and Tamper Evidence (Category I)."""

from tacp.core.audit_service import AuditService
from tacp.domain.audit import AuditEvent
from tacp.infrastructure.database import Database


def test_empty_audit_log(test_db: Database) -> None:
    service = AuditService(test_db)
    events = service.get_recent_events()
    assert events == []


def test_record_and_retrieve_audit_event(test_db: Database) -> None:
    service = AuditService(test_db)
    event = AuditEvent(
        capability="fs.read",
        action="fs.read",
        policy_decision="ALLOWED",
        result="SUCCESS",
        duration_ms=12,
        principal="test-agent",
        workspace_id="ws-abc",
        parameters_redacted={"subpath": "hello.txt"},
    )
    service.record_event(event)

    events = service.get_recent_events(limit=10)
    assert len(events) == 1
    ev = events[0]
    assert ev["capability"] == "fs.read"
    assert ev["principal"] == "test-agent"
    assert ev["workspace_id"] == "ws-abc"
    assert ev["policy_decision"] == "ALLOWED"
    assert ev["result"] == "SUCCESS"
    assert ev["duration_ms"] == 12


def test_audit_events_ordering(test_db: Database) -> None:
    service = AuditService(test_db)
    for i in range(5):
        event = AuditEvent(
            capability=f"cap.{i}",
            action="call",
            policy_decision="ALLOWED",
            result="SUCCESS",
            duration_ms=i,
        )
        service.record_event(event)

    events = service.get_recent_events(limit=10)
    assert len(events) == 5
    # Most recent first
    assert events[0]["capability"] == "cap.4"


def test_audit_limit_enforcement(test_db: Database) -> None:
    service = AuditService(test_db)
    for i in range(15):
        service.record_event(
            AuditEvent(
                capability=f"cap.{i}",
                action="call",
                policy_decision="ALLOWED",
                result="SUCCESS",
                duration_ms=1,
            )
        )

    events = service.get_recent_events(limit=5)
    assert len(events) == 5


def test_audit_parameters_redacted_on_insert(test_db: Database) -> None:
    service = AuditService(test_db)
    service.record_event(
        AuditEvent(
            capability="fs.read",
            action="read",
            policy_decision="ALLOWED",
            result="SUCCESS",
            duration_ms=2,
            parameters_redacted={"token": "sk-ant-secret12345"},
        )
    )

    events = service.get_recent_events(limit=1)
    params = events[0]["parameters"]
    assert "sk-ant-" not in str(params)
    assert params.get("token") == "[REDACTED]"


def test_audit_denied_decision_recorded(test_db: Database) -> None:
    service = AuditService(test_db)
    service.record_event(
        AuditEvent(
            capability="shell.exec",
            action="exec",
            policy_decision="DENIED",
            result="FAILED",
            duration_ms=1,
            parameters_redacted={"cmd": "rm -rf /"},
        )
    )

    events = service.get_recent_events(limit=1)
    assert events[0]["policy_decision"] == "DENIED"
    assert events[0]["result"] == "FAILED"
