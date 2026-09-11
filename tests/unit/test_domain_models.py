"""Tests for TACP Domain Models and Errors (Category B)."""

from pathlib import Path

import pytest

from tacp.domain.audit import AuditEvent
from tacp.domain.capability import Capability
from tacp.domain.classification import DataClassification
from tacp.domain.errors import (
    ErrorCode,
    TacpError,
    TacpNotFoundError,
    TacpSecurityError,
    TacpValidationError,
)
from tacp.domain.workspace import Workspace


def test_data_classification_levels() -> None:
    assert DataClassification.PUBLIC.value == "PUBLIC"
    assert DataClassification.INTERNAL.value == "INTERNAL"
    assert DataClassification.PRIVATE.value == "PRIVATE"
    assert DataClassification.SENSITIVE.value == "SENSITIVE"
    assert DataClassification.SECRET.value == "SECRET"
    assert DataClassification.CRITICAL.value == "CRITICAL"


def test_error_code_enum_values() -> None:
    assert ErrorCode.INVALID_INPUT == "INVALID_INPUT"
    assert ErrorCode.NOT_FOUND == "NOT_FOUND"
    assert ErrorCode.NOT_AUTHORIZED == "NOT_AUTHORIZED"
    assert ErrorCode.OUTSIDE_WORKSPACE == "OUTSIDE_WORKSPACE"
    assert ErrorCode.SECRET_PROTECTED == "SECRET_PROTECTED"
    assert ErrorCode.RESOURCE_LIMIT == "RESOURCE_LIMIT"


def test_tacp_error_to_dict() -> None:
    err = TacpError(ErrorCode.NOT_FOUND, "Resource missing", details={"id": 123})
    d = err.to_dict()
    assert d["error"]["code"] == "NOT_FOUND"
    assert d["error"]["message"] == "Resource missing"
    assert d["error"]["details"]["id"] == 123


def test_tacp_security_error_inheritance() -> None:
    err = TacpSecurityError(ErrorCode.NOT_AUTHORIZED, "Denied")
    assert isinstance(err, TacpError)
    assert err.code == ErrorCode.NOT_AUTHORIZED
    assert err.message == "Denied"


def test_tacp_not_found_error_defaults() -> None:
    err = TacpNotFoundError("Item not found")
    assert err.code == ErrorCode.NOT_FOUND
    assert err.message == "Item not found"


def test_tacp_validation_error_defaults() -> None:
    err = TacpValidationError("Invalid parameter")
    assert err.code == ErrorCode.INVALID_INPUT
    assert err.message == "Invalid parameter"


def test_workspace_model_creation_and_dict(tmp_path: Path) -> None:
    ws = Workspace(
        id="ws-123",
        name="my-workspace",
        root_path=tmp_path,
        trust_level="RESTRICTED",
        status="ACTIVE",
    )
    assert ws.id == "ws-123"
    assert ws.name == "my-workspace"
    d = ws.to_dict()
    assert d["id"] == "ws-123"
    assert d["name"] == "my-workspace"
    assert d["root_path"] == str(tmp_path)
    assert d["status"] == "ACTIVE"


def test_workspace_immutability(tmp_path: Path) -> None:
    from dataclasses import FrozenInstanceError

    ws = Workspace(
        id="ws-123",
        name="my-workspace",
        root_path=tmp_path,
    )
    with pytest.raises(FrozenInstanceError):
        ws.name = "new-name"  # type: ignore[misc]


def test_capability_model_creation_and_dict() -> None:
    cap = Capability(
        name="test.cap",
        domain="test",
        description="Test capability",
        read_only=True,
    )
    assert cap.name == "test.cap"
    d = cap.to_dict()
    assert d["name"] == "test.cap"
    assert d["domain"] == "test"
    assert d["read_only"] is True


def test_audit_event_creation_and_dict() -> None:
    event = AuditEvent(
        capability="fs.read",
        action="fs.read",
        policy_decision="ALLOWED",
        result="SUCCESS",
        duration_ms=5,
        principal="agent-1",
        workspace_id="ws-1",
    )
    assert event.capability == "fs.read"
    d = event.to_dict()
    assert d["capability"] == "fs.read"
    assert d["policy_decision"] == "ALLOWED"
    assert d["result"] == "SUCCESS"
    assert d["principal"] == "agent-1"
