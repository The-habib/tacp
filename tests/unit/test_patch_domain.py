"""Unit tests for Patch and Execution Contract domain models (Category M)."""

from dataclasses import FrozenInstanceError

import pytest

from tacp.domain.contract import ExecutionContract
from tacp.domain.errors import (
    ErrorCode,
    TacpApprovalRequiredError,
    TacpConflictError,
    TacpError,
    TacpPolicyError,
    TacpSecurityError,
)
from tacp.domain.patch import PatchResult, PatchStatus, WorkspacePatch


def test_patch_status_enum_values() -> None:
    assert PatchStatus.PROPOSED == "PROPOSED"
    assert PatchStatus.APPLIED == "APPLIED"
    assert PatchStatus.SIMULATED == "SIMULATED"
    assert PatchStatus.CONFLICT == "CONFLICT"
    assert PatchStatus.APPROVAL_REQUIRED == "APPROVAL_REQUIRED"
    assert PatchStatus.DENIED == "DENIED"
    assert PatchStatus.FAILED == "FAILED"
    assert PatchStatus.ROLLED_BACK == "ROLLED_BACK"


def test_workspace_patch_dataclass_fields() -> None:
    patch = WorkspacePatch(
        patch_id="p-1",
        workspace_id="ws-1",
        subpath="src/main.py",
        base_checksum="abc123",
        patch_content="--- a\n+++ b\n",
        dry_run=True,
        principal_id="agent-1",
        created_at="2026-09-11T00:00:00Z",
        approval_id="appr-1",
    )
    assert patch.patch_id == "p-1"
    assert patch.workspace_id == "ws-1"
    assert patch.subpath == "src/main.py"
    assert patch.base_checksum == "abc123"
    assert patch.dry_run is True
    assert patch.principal_id == "agent-1"
    assert patch.approval_id == "appr-1"

    d = patch.to_dict()
    assert d["patch_id"] == "p-1"
    assert d["workspace_id"] == "ws-1"
    assert d["dry_run"] is True


def test_workspace_patch_immutability() -> None:
    patch = WorkspacePatch(
        patch_id="p-1",
        workspace_id="ws-1",
        subpath="src/main.py",
        base_checksum="abc123",
        patch_content="--- a\n+++ b\n",
    )
    with pytest.raises(FrozenInstanceError):
        patch.dry_run = True  # type: ignore[misc]


def test_patch_result_dataclass_fields() -> None:
    res = PatchResult(
        patch_id="p-1",
        status=PatchStatus.APPLIED,
        subpath="src/main.py",
        before_checksum="abc",
        after_checksum="def",
        lines_added=5,
        lines_removed=2,
        diff_preview="--- a\n+++ b\n",
        audit_id="aud-1",
        message="Patch applied",
        details={"snapshot": "/path/to/snap"},
    )
    assert res.patch_id == "p-1"
    assert res.status == PatchStatus.APPLIED
    assert res.lines_added == 5
    assert res.lines_removed == 2
    d = res.to_dict()
    assert d["status"] == "APPLIED"
    assert d["lines_added"] == 5
    assert d["lines_removed"] == 2
    assert d["details"]["snapshot"] == "/path/to/snap"


def test_execution_contract_dataclass_fields() -> None:
    contract = ExecutionContract(
        contract_id="c-1",
        principal_id="agent-1",
        capability="workspace.patch",
        target_resource="ws-1:src/main.py",
        risk_level="R2",
        approval_id="appr-1",
        status="ACTIVE",
        checksum_before="abc",
    )
    assert contract.contract_id == "c-1"
    assert contract.principal_id == "agent-1"
    assert contract.risk_level == "R2"
    assert contract.status == "ACTIVE"
    d = contract.to_dict()
    assert d["contract_id"] == "c-1"
    assert d["risk_level"] == "R2"


def test_execution_contract_immutability() -> None:
    contract = ExecutionContract(
        contract_id="c-1",
        principal_id="agent-1",
        capability="workspace.patch",
        target_resource="ws-1:src/main.py",
        risk_level="R2",
        status="ACTIVE",
    )
    with pytest.raises(FrozenInstanceError):
        contract.status = "COMPLETED"  # type: ignore[misc]


def test_domain_error_types() -> None:
    err1 = TacpConflictError("Checksum conflict")
    assert err1.code == ErrorCode.CONFLICT
    assert isinstance(err1, TacpError)

    err2 = TacpPolicyError("Policy rejected")
    assert err2.code == ErrorCode.POLICY_DENIED
    assert isinstance(err2, TacpSecurityError)

    err3 = TacpApprovalRequiredError("Human approval needed")
    assert err3.code == ErrorCode.APPROVAL_REQUIRED
    assert isinstance(err3, TacpSecurityError)
