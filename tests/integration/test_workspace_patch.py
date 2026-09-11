"""Integration tests for PatchService 16-stage pipeline (Category M & J)."""

import hashlib
from pathlib import Path
from typing import Any, Dict

import pytest

from tacp.control.approval import ApprovalEngine
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.lock_service import LockService
from tacp.core.patch_service import PatchService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import (
    TacpApprovalRequiredError,
    TacpConflictError,
)
from tacp.domain.patch import PatchStatus
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database
from tacp.providers.filesystem import FilesystemProvider


@pytest.fixture
def patch_env(test_db: Database, tmp_path: Path) -> Dict[str, Any]:
    cfg = TacpConfig(
        data_dir=tmp_path / ".tacp",
        db_path=test_db.db_path,
        mutation_enabled=True,
        read_only=False,
    )
    ws_dir = tmp_path / "my_project"
    ws_dir.mkdir()
    (ws_dir / "src").mkdir()
    (ws_dir / "src" / "app.py").write_text("def run():\n    return 1\n")

    ws_service = WorkspaceService(test_db)
    ws = ws_service.register_workspace("test_proj", ws_dir)

    policy_engine = PolicyEngine(mutation_enabled=True, read_only_enforced=False)
    audit_service = AuditService(test_db)
    fs_provider = FilesystemProvider(limits=cfg.limits)
    lock_service = LockService(test_db)
    approval_engine = ApprovalEngine(test_db)

    patch_service = PatchService(
        db=test_db,
        workspace_service=ws_service,
        policy_engine=policy_engine,
        fs_provider=fs_provider,
        audit_service=audit_service,
        lock_service=lock_service,
        approval_engine=approval_engine,
        config=cfg,
    )

    return {
        "patch_service": patch_service,
        "approval_engine": approval_engine,
        "audit_service": audit_service,
        "workspace": ws,
        "ws_dir": ws_dir,
    }


def test_end_to_end_dry_run_patch(patch_env: Dict[str, Any]) -> None:
    service: PatchService = patch_env["patch_service"]
    ws = patch_env["workspace"]
    target_file = patch_env["ws_dir"] / "src" / "app.py"
    base_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()

    diff = (
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def run():\n"
        "-    return 1\n"
        "+    return 2\n"
    )

    res = service.execute_patch(
        workspace_id=ws.id,
        subpath="src/app.py",
        patch_content=diff,
        base_checksum=base_hash,
        dry_run=True,
    )
    assert res.status == PatchStatus.SIMULATED
    assert res.lines_added == 1
    assert res.lines_removed == 1
    assert target_file.read_text() == "def run():\n    return 1\n"


def test_end_to_end_live_patch_with_approval(patch_env: Dict[str, Any]) -> None:
    service: PatchService = patch_env["patch_service"]
    appr_engine: ApprovalEngine = patch_env["approval_engine"]
    ws = patch_env["workspace"]
    target_file = patch_env["ws_dir"] / "src" / "app.py"
    base_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()

    diff = (
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def run():\n"
        "-    return 1\n"
        "+    return 2\n"
    )
    diff_hash = hashlib.sha256(diff.encode("utf-8")).hexdigest()

    ticket = appr_engine.create_ticket(
        principal_id="agent",
        action_type="workspace.patch",
        workspace_id=ws.id,
        target_path="src/app.py",
        patch_hash=diff_hash,
    )
    appr_engine.approve(ticket.token)

    res = service.execute_patch(
        workspace_id=ws.id,
        subpath="src/app.py",
        patch_content=diff,
        base_checksum=base_hash,
        dry_run=False,
        approval_token=ticket.token,
    )
    assert res.status == PatchStatus.APPLIED
    assert res.lines_added == 1
    assert res.lines_removed == 1
    assert target_file.read_text() == "def run():\n    return 2\n"

    # Ticket should now be CONSUMED
    updated_ticket = appr_engine.get_ticket(ticket.token)
    assert updated_ticket is not None
    assert updated_ticket.status == "CONSUMED"


def test_live_patch_missing_approval_raises(patch_env: Dict[str, Any]) -> None:
    service: PatchService = patch_env["patch_service"]
    ws = patch_env["workspace"]
    target_file = patch_env["ws_dir"] / "src" / "app.py"
    base_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()

    diff = (
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def run():\n"
        "-    return 1\n"
        "+    return 2\n"
    )

    with pytest.raises(TacpApprovalRequiredError) as exc_info:
        service.execute_patch(
            workspace_id=ws.id,
            subpath="src/app.py",
            patch_content=diff,
            base_checksum=base_hash,
            dry_run=False,
            approval_token=None,
        )
    assert "requires explicit human approval" in str(exc_info.value)
    assert "Ticket created" in str(exc_info.value)


def test_patch_rollback(patch_env: Dict[str, Any]) -> None:
    service: PatchService = patch_env["patch_service"]
    appr_engine: ApprovalEngine = patch_env["approval_engine"]
    ws = patch_env["workspace"]
    target_file = patch_env["ws_dir"] / "src" / "app.py"
    orig_text = target_file.read_text()
    base_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()

    diff = (
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def run():\n"
        "-    return 1\n"
        "+    return 2\n"
    )
    diff_hash = hashlib.sha256(diff.encode("utf-8")).hexdigest()

    ticket = appr_engine.create_ticket(
        principal_id="agent",
        action_type="workspace.patch",
        workspace_id=ws.id,
        target_path="src/app.py",
        patch_hash=diff_hash,
    )
    appr_engine.approve(ticket.token)

    res = service.execute_patch(
        workspace_id=ws.id,
        subpath="src/app.py",
        patch_content=diff,
        base_checksum=base_hash,
        dry_run=False,
        approval_token=ticket.token,
    )
    assert target_file.read_text() == "def run():\n    return 2\n"

    # Rollback
    rollback_res = service.rollback_patch(res.patch_id)
    assert rollback_res.status == PatchStatus.ROLLED_BACK
    assert target_file.read_text() == orig_text

    # Double rollback should fail
    with pytest.raises(TacpConflictError):
        service.rollback_patch(res.patch_id)


def test_list_and_get_patches(patch_env: Dict[str, Any]) -> None:
    service: PatchService = patch_env["patch_service"]
    appr_engine: ApprovalEngine = patch_env["approval_engine"]
    ws = patch_env["workspace"]
    target_file = patch_env["ws_dir"] / "src" / "app.py"
    base_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()

    diff = (
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def run():\n"
        "-    return 1\n"
        "+    return 2\n"
    )
    diff_hash = hashlib.sha256(diff.encode("utf-8")).hexdigest()

    ticket = appr_engine.create_ticket(
        principal_id="agent",
        action_type="workspace.patch",
        workspace_id=ws.id,
        target_path="src/app.py",
        patch_hash=diff_hash,
    )
    appr_engine.approve(ticket.token)

    res = service.execute_patch(
        workspace_id=ws.id,
        subpath="src/app.py",
        patch_content=diff,
        base_checksum=base_hash,
        dry_run=False,
        approval_token=ticket.token,
    )

    patches = service.list_patches(workspace_id=ws.id)
    assert len(patches) >= 1
    assert patches[0]["id"] == res.patch_id

    patch_detail = service.get_patch(res.patch_id)
    assert patch_detail is not None
    assert patch_detail["id"] == res.patch_id
    assert patch_detail["status"] == "APPLIED"
