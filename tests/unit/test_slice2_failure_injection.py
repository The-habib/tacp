"""Failure injection test suite for TACP Slice 2 (F0 to F15)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest

from tacp.control.approval import ApprovalEngine, compute_canonical_batch_hash
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.lock_service import LockService
from tacp.core.patch_service import PatchService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import (
    ErrorCode,
    TacpConflictError,
    TacpNotFoundError,
    TacpSecurityError,
    TacpValidationError,
)
from tacp.infrastructure.config import OutputLimits, TacpConfig
from tacp.infrastructure.database import Database
from tacp.providers.filesystem import FilesystemProvider


@pytest.fixture
def fi_env(tmp_path: Path) -> Dict[str, Any]:
    data_dir = tmp_path / ".tacp"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "tacp.db"
    config = TacpConfig(
        data_dir=data_dir,
        db_path=db_path,
        mutation_enabled=True,
        batch_mutation_enabled=True,
        read_only=False,
        limits=OutputLimits(
            max_batch_files=5,
            max_batch_patch_total_bytes=10000,
            max_batch_resulting_total_bytes=50000,
            max_patch_bytes=5000,
            max_file_size_bytes=10000,
            max_resulting_file_bytes=20000,
        ),
    )
    db = Database(db_path)
    db.connect()
    ws_service = WorkspaceService(db)
    policy_engine = PolicyEngine(
        read_only_enforced=False,
        mutation_enabled=True,
        batch_mutation_enabled=True,
    )
    fs_provider = FilesystemProvider(limits=config.limits)
    audit_service = AuditService(db)
    lock_service = LockService(db)
    approval_engine = ApprovalEngine(db)

    ws_root = tmp_path / "workspace"
    ws_root.mkdir(parents=True, exist_ok=True)
    ws = ws_service.register_workspace(name="ws", root_path=ws_root)

    patch_service = PatchService(
        db=db,
        workspace_service=ws_service,
        policy_engine=policy_engine,
        fs_provider=fs_provider,
        audit_service=audit_service,
        lock_service=lock_service,
        approval_engine=approval_engine,
        config=config,
    )

    return {
        "patch_service": patch_service,
        "ws": ws,
        "fs_provider": fs_provider,
        "approval_engine": approval_engine,
        "ws_root": ws_root,
    }


def _run_batch(env: Dict[str, Any], patches: List[Dict[str, Any]], dry_run: bool = False) -> Any:
    ps = env["patch_service"]
    ws = env["ws"]
    ae = env["approval_engine"]
    if dry_run:
        return ps.execute_patch_batch(workspace_id=ws.id, patches=patches, dry_run=True)
    b_hash = compute_canonical_batch_hash(patches)
    ticket = ae.create_ticket("tester", "workspace.patch_batch", ws.id, "*", b_hash)
    ae.approve(ticket.token)
    return ps.execute_patch_batch(
        workspace_id=ws.id,
        patches=patches,
        dry_run=False,
        approval_token=ticket.token,
        principal_id="tester",
    )


# F0: Preflight file not found
def test_f00_file_not_found(fi_env: Dict[str, Any]) -> None:
    patches = [{"subpath": "missing.txt", "patch_content": "+x\n", "base_checksum": "000"}]
    with pytest.raises(TacpNotFoundError) as exc:
        _run_batch(fi_env, patches, dry_run=True)
    assert "does not exist" in str(exc.value)


# F1: Preflight directory as target
def test_f01_directory_as_target(fi_env: Dict[str, Any]) -> None:
    d = fi_env["ws_root"] / "subdir"
    d.mkdir()
    patches = [{"subpath": "subdir", "patch_content": "+x\n", "base_checksum": "000"}]
    with pytest.raises(TacpValidationError) as exc:
        _run_batch(fi_env, patches, dry_run=True)
    assert "directory, not a file" in str(exc.value)


# F2: Preflight symlink target
def test_f02_symlink_target(fi_env: Dict[str, Any]) -> None:
    target = fi_env["ws_root"] / "real.txt"
    target.write_text("hello\n")
    link = fi_env["ws_root"] / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Symlink not supported")
    patches = [{"subpath": "link.txt", "patch_content": "+x\n", "base_checksum": "000"}]
    with pytest.raises(TacpSecurityError) as exc:
        _run_batch(fi_env, patches, dry_run=True)
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


# F3: Preflight secret classification
def test_f03_secret_classification(fi_env: Dict[str, Any]) -> None:
    secret_f = fi_env["ws_root"] / "config_secret.pem"
    secret_f.write_text(
        "-----" + "BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----" + "END RSA PRIVATE KEY-----\n"
    )
    c = hashlib.sha256(secret_f.read_bytes()).hexdigest()
    patches = [
        {
            "subpath": "config_secret.pem",
            "patch_content": "--- a\n+++ a\n@@ -1 +1 @@\n-x\n+y\n",
            "base_checksum": c,
        }
    ]
    with pytest.raises(TacpSecurityError) as exc:
        fi_env["fs_provider"].apply_patch_batch(fi_env["ws_root"], patches, dry_run=True)
    assert exc.value.code == ErrorCode.POLICY_DENIED


# F4: Preflight diff format corrupt
def test_f04_diff_corrupt(fi_env: Dict[str, Any]) -> None:
    f = fi_env["ws_root"] / "c.txt"
    f.write_text("hello\n")
    c = hashlib.sha256(f.read_bytes()).hexdigest()
    patches = [
        {
            "subpath": "c.txt",
            "patch_content": "invalid diff header without hunks",
            "base_checksum": c,
        }
    ]
    with pytest.raises(TacpValidationError):
        _run_batch(fi_env, patches, dry_run=True)


# F5: Preflight OCC checksum mismatch
def test_f05_occ_checksum_mismatch(fi_env: Dict[str, Any]) -> None:
    f = fi_env["ws_root"] / "occ.txt"
    f.write_text("content\n")
    diff = "--- a\n+++ a\n@@ -1 +1 @@\n-content\n+mod\n"
    patches = [{"subpath": "occ.txt", "patch_content": diff, "base_checksum": "wrong_checksum"}]
    with pytest.raises(TacpConflictError):
        _run_batch(fi_env, patches, dry_run=True)


# F6: Preflight non-UTF8 target
def test_f06_non_utf8_target(fi_env: Dict[str, Any]) -> None:
    f = fi_env["ws_root"] / "binary.bin"
    f.write_bytes(b"\xff\xfe\x00\x00non_utf8")
    c = hashlib.sha256(f.read_bytes()).hexdigest()
    patches = [
        {
            "subpath": "binary.bin",
            "patch_content": "--- a\n+++ a\n@@ -1 +1 @@\n-x\n+y\n",
            "base_checksum": c,
        }
    ]
    with pytest.raises(TacpValidationError):
        _run_batch(fi_env, patches, dry_run=True)


# F7: Preflight diff size exceeded
def test_f07_diff_size_exceeded(fi_env: Dict[str, Any]) -> None:
    f = fi_env["ws_root"] / "small.txt"
    f.write_text("line\n")
    c = hashlib.sha256(f.read_bytes()).hexdigest()
    big_diff = "--- a\n+++ a\n@@ -1 +1,2 @@\n line\n+" + ("X" * 6000) + "\n"
    patches = [{"subpath": "small.txt", "patch_content": big_diff, "base_checksum": c}]
    with pytest.raises(TacpValidationError) as exc:
        _run_batch(fi_env, patches, dry_run=True)
    assert "exceeds limit" in str(exc.value)


# F8: Preflight aggregate diff size exceeded
def test_f08_aggregate_diff_size_exceeded(fi_env: Dict[str, Any]) -> None:
    f1 = fi_env["ws_root"] / "a1.txt"
    f2 = fi_env["ws_root"] / "a2.txt"
    f3 = fi_env["ws_root"] / "a3.txt"
    f1.write_text("a\n")
    f2.write_text("b\n")
    f3.write_text("c\n")
    c1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    c2 = hashlib.sha256(f2.read_bytes()).hexdigest()
    c3 = hashlib.sha256(f3.read_bytes()).hexdigest()
    diff1 = "--- a\n+++ a\n@@ -1 +1,2 @@\n a\n+" + ("X" * 3800) + "\n"
    diff2 = "--- b\n+++ b\n@@ -1 +1,2 @@\n b\n+" + ("Y" * 3800) + "\n"
    diff3 = "--- c\n+++ c\n@@ -1 +1,2 @@\n c\n+" + ("Z" * 3800) + "\n"
    patches = [
        {"subpath": "a1.txt", "patch_content": diff1, "base_checksum": c1},
        {"subpath": "a2.txt", "patch_content": diff2, "base_checksum": c2},
        {"subpath": "a3.txt", "patch_content": diff3, "base_checksum": c3},
    ]
    with pytest.raises(TacpValidationError) as exc:
        _run_batch(fi_env, patches, dry_run=True)
    assert "Total batch patch diff size" in str(exc.value)


# F9: Staging snapshot failure injection (simulated OSError on snapshot creation)
def test_f09_snapshot_creation_failure(
    fi_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    f = fi_env["ws_root"] / "snap_fail.txt"
    f.write_text("snap text\n")
    c = hashlib.sha256(f.read_bytes()).hexdigest()
    diff = "--- a\n+++ a\n@@ -1 +1 @@\n-snap text\n+modified\n"
    patches = [{"subpath": "snap_fail.txt", "patch_content": diff, "base_checksum": c}]

    orig_write_bytes = Path.write_bytes

    def mock_write_bytes(self: Path, data: bytes) -> int:
        if "snapshots" in str(self):
            raise OSError("Disk full during snapshot")
        return orig_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", mock_write_bytes)

    with pytest.raises(TacpSecurityError) as exc:
        _run_batch(fi_env, patches, dry_run=False)
    assert "Failed to create pre-patch snapshot" in str(exc.value)


# F10: Staging disk full injection (simulated write failure on temp file)
def test_f10_staging_temp_write_failure(
    fi_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    f = fi_env["ws_root"] / "stage_fail.txt"
    f.write_text("stage text\n")
    c = hashlib.sha256(f.read_bytes()).hexdigest()
    diff = "--- a\n+++ a\n@@ -1 +1 @@\n-stage text\n+modified\n"
    patches = [{"subpath": "stage_fail.txt", "patch_content": diff, "base_checksum": c}]

    orig_open = Path.open

    def mock_open(self: Path, mode: str = "r", **kwargs: Any) -> Any:
        if ".tacp_tmp_" in self.name and "w" in mode:
            raise OSError("Disk write error during staging")
        return orig_open(self, mode, **kwargs)

    monkeypatch.setattr(Path, "open", mock_open)

    with pytest.raises(TacpSecurityError) as exc:
        _run_batch(fi_env, patches, dry_run=False)
    assert "Batch staging failed" in str(exc.value)


# F11: Commit phase failure injection on file 2 (verifies file 1 rolled back)
def test_f11_commit_replace_failure_rolls_back(
    fi_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    f1 = fi_env["ws_root"] / "c1.txt"
    f2 = fi_env["ws_root"] / "c2.txt"
    f1.write_text("c1 original\n")
    f2.write_text("c2 original\n")
    c1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    c2 = hashlib.sha256(f2.read_bytes()).hexdigest()

    diff1 = "--- a\n+++ a\n@@ -1 +1 @@\n-c1 original\n+c1 NEW\n"
    diff2 = "--- b\n+++ b\n@@ -1 +1 @@\n-c2 original\n+c2 NEW\n"
    patches = [
        {"subpath": "c1.txt", "patch_content": diff1, "base_checksum": c1},
        {"subpath": "c2.txt", "patch_content": diff2, "base_checksum": c2},
    ]

    orig_replace = os.replace
    call_count = 0

    def mock_replace(src: Any, dst: Any) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("Injected commit failure on file 2")
        orig_replace(src, dst)

    monkeypatch.setattr(os, "replace", mock_replace)

    with pytest.raises(TacpSecurityError) as exc:
        _run_batch(fi_env, patches, dry_run=False)
    assert "Batch commit failed; all modified files rolled back" in str(exc.value)
    assert f1.read_text() == "c1 original\n"
    assert f2.read_text() == "c2 original\n"


# F12: Post-write checksum verification failure (simulated corruption)
def test_f12_post_write_verification_failure(
    fi_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    f = fi_env["ws_root"] / "verify_corrupt.txt"
    f.write_text("orig\n")
    c = hashlib.sha256(f.read_bytes()).hexdigest()
    diff = "--- a\n+++ a\n@@ -1 +1 @@\n-orig\n+modified\n"
    patches = [{"subpath": "verify_corrupt.txt", "patch_content": diff, "base_checksum": c}]

    orig_read_bytes = Path.read_bytes
    orig_replace = os.replace
    post_commit = False
    corrupted_once = False

    def mock_replace(src: Any, dst: Any) -> None:
        nonlocal post_commit
        orig_replace(src, dst)
        post_commit = True

    def mock_read_bytes(self: Path) -> bytes:
        nonlocal corrupted_once
        if post_commit and not corrupted_once and self.name == "verify_corrupt.txt":
            corrupted_once = True
            return b"corrupted bytes from disk"
        return orig_read_bytes(self)

    monkeypatch.setattr(os, "replace", mock_replace)
    monkeypatch.setattr(Path, "read_bytes", mock_read_bytes)

    with pytest.raises(TacpSecurityError) as exc:
        _run_batch(fi_env, patches, dry_run=False)
    assert "Batch commit failed; all modified files rolled back" in str(exc.value)
    assert "Post-write verification failed" in str(exc.value)
    assert f.read_text() == "orig\n"


# F13: Rollback snapshot missing
def test_f13_rollback_snapshot_missing(fi_env: Dict[str, Any]) -> None:
    f = fi_env["ws_root"] / "rb_miss.txt"
    f.write_text("val\n")
    c = hashlib.sha256(f.read_bytes()).hexdigest()
    diff = "--- a\n+++ a\n@@ -1 +1 @@\n-val\n+val2\n"
    res = _run_batch(
        fi_env, [{"subpath": "rb_miss.txt", "patch_content": diff, "base_checksum": c}]
    )

    # Delete snapshot from disk
    manifest = res.details["snapshot_manifest"]
    snap_path = Path(manifest["rb_miss.txt"])
    snap_path.unlink()

    with pytest.raises(TacpNotFoundError) as exc:
        fi_env["patch_service"].rollback_batch(res.batch_id)
    assert "Snapshot file not found" in str(exc.value)


# F14: Rollback checksum conflict (file changed since batch applied)
def test_f14_rollback_checksum_conflict(fi_env: Dict[str, Any]) -> None:
    f = fi_env["ws_root"] / "rb_drift.txt"
    f.write_text("drift1\n")
    c = hashlib.sha256(f.read_bytes()).hexdigest()
    diff = "--- a\n+++ a\n@@ -1 +1 @@\n-drift1\n+drift2\n"
    res = _run_batch(
        fi_env, [{"subpath": "rb_drift.txt", "patch_content": diff, "base_checksum": c}]
    )

    # Tamper with file
    f.write_text("drift_modified_by_other\n")

    with pytest.raises(TacpConflictError) as exc:
        fi_env["patch_service"].rollback_batch(res.batch_id)
    assert "Rollback conflict" in str(exc.value)


# F15: Rollback atomic restore failure
def test_f15_rollback_atomic_restore_failure(
    fi_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    f = fi_env["ws_root"] / "rb_fail.txt"
    f.write_text("rb1\n")
    c = hashlib.sha256(f.read_bytes()).hexdigest()
    diff = "--- a\n+++ a\n@@ -1 +1 @@\n-rb1\n+rb2\n"
    res = _run_batch(
        fi_env, [{"subpath": "rb_fail.txt", "patch_content": diff, "base_checksum": c}]
    )

    orig_replace = os.replace

    def mock_replace(src: Any, dst: Any) -> None:
        if ".tacp_tmp_rb_" in str(src):
            raise OSError("Rollback replace failure")
        orig_replace(src, dst)

    monkeypatch.setattr(os, "replace", mock_replace)

    with pytest.raises(TacpSecurityError) as exc:
        fi_env["patch_service"].rollback_batch(res.batch_id)
    assert exc.value.code == ErrorCode.ROLLBACK_FAILED
