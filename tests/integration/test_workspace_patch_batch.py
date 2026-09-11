"""Integration tests for workspace.patch_batch capability."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tacp.control.approval import ApprovalEngine, compute_canonical_batch_hash
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.lock_service import LockService
from tacp.core.patch_service import PatchService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import (
    TacpApprovalRequiredError,
    TacpConflictError,
    TacpValidationError,
)
from tacp.domain.patch import PatchStatus
from tacp.infrastructure.config import OutputLimits, TacpConfig
from tacp.infrastructure.database import Database
from tacp.providers.filesystem import FilesystemProvider


@pytest.fixture
def test_config(tmp_path: Path) -> TacpConfig:
    data_dir = tmp_path / ".tacp"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "tacp.db"
    return TacpConfig(
        data_dir=data_dir,
        db_path=db_path,
        mutation_enabled=True,
        batch_mutation_enabled=True,
        read_only=False,
        limits=OutputLimits(
            max_batch_files=5,
            max_batch_patch_total_bytes=10000,
            max_batch_resulting_total_bytes=50000,
        ),
    )


@pytest.fixture
def patch_service(test_config: TacpConfig, tmp_path: Path) -> PatchService:
    db = Database(test_config.db_path)
    db.connect()
    ws_service = WorkspaceService(db)
    policy_engine = PolicyEngine(
        read_only_enforced=False,
        mutation_enabled=True,
        batch_mutation_enabled=True,
    )
    fs_provider = FilesystemProvider(limits=test_config.limits)
    audit_service = AuditService(db)
    lock_service = LockService(db)
    approval_engine = ApprovalEngine(db)

    # Register test workspace
    ws_root = tmp_path / "workspace"
    ws_root.mkdir(parents=True, exist_ok=True)
    ws_service.register_workspace(name="test-ws", root_path=ws_root)

    return PatchService(
        db=db,
        workspace_service=ws_service,
        policy_engine=policy_engine,
        fs_provider=fs_provider,
        audit_service=audit_service,
        lock_service=lock_service,
        approval_engine=approval_engine,
        config=test_config,
    )


def test_batch_patch_dry_run(patch_service: PatchService) -> None:
    ws_id = patch_service.workspace_service.list_workspaces()[0]["id"]
    ws = patch_service.workspace_service.get_workspace(ws_id)
    root = ws.root_path

    f1 = root / "file1.txt"
    f2 = root / "file2.txt"
    f1.write_text("line 1\nline 2\n")
    f2.write_text("alpha\nbeta\n")

    c1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    c2 = hashlib.sha256(f2.read_bytes()).hexdigest()

    diff1 = "--- file1.txt\n+++ file1.txt\n@@ -1,2 +1,3 @@\n line 1\n+line 1.5\n line 2\n"
    diff2 = "--- file2.txt\n+++ file2.txt\n@@ -1,2 +1,2 @@\n-alpha\n+omega\n beta\n"

    patches = [
        {"subpath": "file1.txt", "patch_content": diff1, "base_checksum": c1},
        {"subpath": "file2.txt", "patch_content": diff2, "base_checksum": c2},
    ]

    res = patch_service.execute_patch_batch(
        workspace_id=ws.id,
        patches=patches,
        dry_run=True,
    )

    assert res.status == PatchStatus.SIMULATED
    assert len(res.results) == 2
    assert res.changed_files == ["file1.txt", "file2.txt"]

    # Disks must NOT be modified
    assert f1.read_text() == "line 1\nline 2\n"
    assert f2.read_text() == "alpha\nbeta\n"


def test_batch_patch_requires_approval_and_succeeds_with_approval(
    patch_service: PatchService,
) -> None:
    ws_id = patch_service.workspace_service.list_workspaces()[0]["id"]
    ws = patch_service.workspace_service.get_workspace(ws_id)
    root = ws.root_path

    f1 = root / "a.py"
    f2 = root / "b.py"
    f3 = root / "c.py"
    f1.write_text("print('a')\n")
    f2.write_text("print('b')\n")
    f3.write_text("print('c')\n")

    c1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    c2 = hashlib.sha256(f2.read_bytes()).hexdigest()
    c3 = hashlib.sha256(f3.read_bytes()).hexdigest()

    diff1 = "--- a.py\n+++ a.py\n@@ -1 +1,2 @@\n print('a')\n+print('a2')\n"
    diff2 = "--- b.py\n+++ b.py\n@@ -1 +1 @@\n-print('b')\n+print('b_mod')\n"
    diff3 = "--- c.py\n+++ c.py\n@@ -1 +1,2 @@\n+print('c0')\n print('c')\n"

    patches = [
        {"subpath": "a.py", "patch_content": diff1, "base_checksum": c1},
        {"subpath": "b.py", "patch_content": diff2, "base_checksum": c2},
        {"subpath": "c.py", "patch_content": diff3, "base_checksum": c3},
    ]

    # Without approval -> raises TacpApprovalRequiredError
    with pytest.raises(TacpApprovalRequiredError) as exc_info:
        patch_service.execute_patch_batch(
            workspace_id=ws.id,
            patches=patches,
            dry_run=False,
            principal_id="test-agent",
        )
    assert "requires explicit human approval" in str(exc_info.value)

    # Approve the created ticket
    batch_hash = compute_canonical_batch_hash(patches)
    ticket = patch_service.approval_engine.create_ticket(
        principal_id="test-agent",
        action_type="workspace.patch_batch",
        workspace_id=ws.id,
        target_path="*",
        patch_hash=batch_hash,
    )
    patch_service.approval_engine.approve(ticket.token)

    # Execute with valid approval token
    res = patch_service.execute_patch_batch(
        workspace_id=ws.id,
        patches=patches,
        dry_run=False,
        approval_token=ticket.token,
        principal_id="test-agent",
    )

    assert res.status == PatchStatus.APPLIED
    assert len(res.results) == 3
    assert f1.read_text() == "print('a')\nprint('a2')\n"
    assert f2.read_text() == "print('b_mod')\n"
    assert f3.read_text() == "print('c0')\nprint('c')\n"

    # Verify batch DB persistence
    batch_record = patch_service.get_batch(res.batch_id)
    assert batch_record is not None
    assert batch_record["patch_count"] == 3
    assert batch_record["status"] == "APPLIED"

    # Verify batch listing
    batches = patch_service.list_batches(workspace_id=ws.id)
    assert len(batches) >= 1
    assert batches[0]["id"] == res.batch_id


def test_batch_patch_occ_conflict_aborts_entire_batch(patch_service: PatchService) -> None:
    ws_id = patch_service.workspace_service.list_workspaces()[0]["id"]
    ws = patch_service.workspace_service.get_workspace(ws_id)
    root = ws.root_path

    f1 = root / "f1.txt"
    f2 = root / "f2.txt"
    f1.write_text("initial 1\n")
    f2.write_text("initial 2\n")

    c1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    wrong_c2 = "0000000000000000000000000000000000000000000000000000000000000000"

    diff1 = "--- f1.txt\n+++ f1.txt\n@@ -1 +1,2 @@\n initial 1\n+mod\n"
    diff2 = "--- f2.txt\n+++ f2.txt\n@@ -1 +1,2 @@\n initial 2\n+mod\n"

    patches = [
        {"subpath": "f1.txt", "patch_content": diff1, "base_checksum": c1},
        {"subpath": "f2.txt", "patch_content": diff2, "base_checksum": wrong_c2},
    ]

    batch_hash = compute_canonical_batch_hash(patches)
    ticket = patch_service.approval_engine.create_ticket(
        principal_id="test-agent",
        action_type="workspace.patch_batch",
        workspace_id=ws.id,
        target_path="*",
        patch_hash=batch_hash,
    )
    patch_service.approval_engine.approve(ticket.token)

    with pytest.raises(TacpConflictError) as exc:
        patch_service.execute_patch_batch(
            workspace_id=ws.id,
            patches=patches,
            dry_run=False,
            approval_token=ticket.token,
            principal_id="test-agent",
        )
    assert "Base checksum mismatch for 'f2.txt'" in str(exc.value)

    # Invariant: File 1 MUST NOT have been modified on disk
    assert f1.read_text() == "initial 1\n"
    assert f2.read_text() == "initial 2\n"


def test_batch_patch_target_aliasing_denied(patch_service: PatchService) -> None:
    ws_id = patch_service.workspace_service.list_workspaces()[0]["id"]
    ws = patch_service.workspace_service.get_workspace(ws_id)

    patches = [
        {"subpath": "foo/bar.txt", "patch_content": "...", "base_checksum": "abc"},
        {"subpath": "./foo/bar.txt", "patch_content": "...", "base_checksum": "abc"},
    ]

    with pytest.raises(TacpValidationError) as exc:
        patch_service.execute_patch_batch(
            workspace_id=ws.id,
            patches=patches,
            dry_run=True,
        )
    assert "Duplicate subpath in batch request" in str(exc.value)


def test_batch_rollback_restores_all_files(patch_service: PatchService) -> None:
    ws_id = patch_service.workspace_service.list_workspaces()[0]["id"]
    ws = patch_service.workspace_service.get_workspace(ws_id)
    root = ws.root_path

    f1 = root / "doc1.txt"
    f2 = root / "doc2.txt"
    orig_text1 = "Document 1 original\n"
    orig_text2 = "Document 2 original\n"
    f1.write_text(orig_text1)
    f2.write_text(orig_text2)

    c1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    c2 = hashlib.sha256(f2.read_bytes()).hexdigest()

    diff1 = "--- doc1.txt\n+++ doc1.txt\n@@ -1 +1 @@\n-Document 1 original\n+Document 1 mutated\n"
    diff2 = "--- doc2.txt\n+++ doc2.txt\n@@ -1 +1 @@\n-Document 2 original\n+Document 2 mutated\n"

    patches = [
        {"subpath": "doc1.txt", "patch_content": diff1, "base_checksum": c1},
        {"subpath": "doc2.txt", "patch_content": diff2, "base_checksum": c2},
    ]

    batch_hash = compute_canonical_batch_hash(patches)
    ticket = patch_service.approval_engine.create_ticket(
        principal_id="test-agent",
        action_type="workspace.patch_batch",
        workspace_id=ws.id,
        target_path="*",
        patch_hash=batch_hash,
    )
    patch_service.approval_engine.approve(ticket.token)

    apply_res = patch_service.execute_patch_batch(
        workspace_id=ws.id,
        patches=patches,
        dry_run=False,
        approval_token=ticket.token,
        principal_id="test-agent",
    )
    assert apply_res.status == PatchStatus.APPLIED
    assert f1.read_text() == "Document 1 mutated\n"
    assert f2.read_text() == "Document 2 mutated\n"

    # Roll back the batch
    rb_res = patch_service.rollback_batch(apply_res.batch_id, principal_id="operator")
    assert rb_res.status == PatchStatus.ROLLED_BACK
    assert len(rb_res.results) == 2

    # Verify both files are restored to exact original contents
    assert f1.read_text() == orig_text1
    assert f2.read_text() == orig_text2

    # Attempting to rollback again should fail
    with pytest.raises(TacpConflictError):
        patch_service.rollback_batch(apply_res.batch_id, principal_id="operator")
