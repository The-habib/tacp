"""Comprehensive security test suite for TACP Slice 2 (SB-01 to SB-40)."""

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
from tacp.domain.patch import PatchStatus
from tacp.infrastructure.config import OutputLimits, TacpConfig
from tacp.infrastructure.database import Database
from tacp.providers.filesystem import FilesystemProvider


@pytest.fixture
def sec_config(tmp_path: Path) -> TacpConfig:
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
            max_batch_files=10,
            max_batch_patch_total_bytes=1048576,
            max_batch_resulting_total_bytes=5242880,
            max_patch_bytes=262144,
            max_file_size_bytes=1048576,
            max_resulting_file_bytes=2097152,
        ),
    )


@pytest.fixture
def sec_env(sec_config: TacpConfig, tmp_path: Path) -> Dict[str, Any]:
    db = Database(sec_config.db_path)
    db.connect()
    ws_service = WorkspaceService(db)
    policy_engine = PolicyEngine(
        read_only_enforced=False,
        mutation_enabled=True,
        batch_mutation_enabled=True,
    )
    fs_provider = FilesystemProvider(limits=sec_config.limits)
    audit_service = AuditService(db)
    lock_service = LockService(db)
    approval_engine = ApprovalEngine(db)

    ws_root1 = tmp_path / "ws1"
    ws_root1.mkdir(parents=True, exist_ok=True)
    ws1 = ws_service.register_workspace(name="ws1", root_path=ws_root1)

    ws_root2 = tmp_path / "ws2"
    ws_root2.mkdir(parents=True, exist_ok=True)
    ws2 = ws_service.register_workspace(name="ws2", root_path=ws_root2)

    patch_service = PatchService(
        db=db,
        workspace_service=ws_service,
        policy_engine=policy_engine,
        fs_provider=fs_provider,
        audit_service=audit_service,
        lock_service=lock_service,
        approval_engine=approval_engine,
        config=sec_config,
    )

    return {
        "patch_service": patch_service,
        "ws1": ws1,
        "ws2": ws2,
        "approval_engine": approval_engine,
        "db": db,
        "config": sec_config,
    }


def _approve_and_exec(
    env: Dict[str, Any], ws_id: str, patches: List[Dict[str, Any]], dry_run: bool = False
) -> Any:
    ps = env["patch_service"]
    ae = env["approval_engine"]
    if dry_run:
        return ps.execute_patch_batch(workspace_id=ws_id, patches=patches, dry_run=True)
    batch_hash = compute_canonical_batch_hash(patches)
    ticket = ae.create_ticket(
        principal_id="test-agent",
        action_type="workspace.patch_batch",
        workspace_id=ws_id,
        target_path="*",
        patch_hash=batch_hash,
    )
    ae.approve(ticket.token)
    return ps.execute_patch_batch(
        workspace_id=ws_id,
        patches=patches,
        dry_run=False,
        approval_token=ticket.token,
        principal_id="test-agent",
    )


# SB-01: Cross-workspace batch injection
def test_sb01_cross_workspace_injection(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    ws2 = sec_env["ws2"]
    f2 = ws2.root_path / "ws2_target.txt"
    f2.write_text("ws2 content\n")
    c2 = hashlib.sha256(f2.read_bytes()).hexdigest()

    # Attempting to target ws2 file via relative escape from ws1
    rel_escape = f"../ws2/{f2.name}"
    patches = [
        {
            "subpath": rel_escape,
            "patch_content": "--- a\n+++ a\n@@ -1 +1 @@\n-ws2\n+hack\n",
            "base_checksum": c2,
        }
    ]
    with pytest.raises(TacpSecurityError):
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)


# SB-02: Target aliasing (duplicate targets in single batch)
def test_sb02_target_aliasing_denied(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = [
        {"subpath": "foo/bar.txt", "patch_content": "+line\n", "base_checksum": "abc"},
        {"subpath": "foo/../foo/bar.txt", "patch_content": "+line\n", "base_checksum": "abc"},
    ]
    with pytest.raises((TacpValidationError, TacpSecurityError)) as exc:
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)
    assert "Duplicate subpath" in str(exc.value) or "traversal" in str(exc.value).lower()


# SB-03: Circular symlink target inside batch
def test_sb03_circular_symlink_denied(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    link_a = ws1.root_path / "link_a"
    link_b = ws1.root_path / "link_b"
    try:
        link_a.symlink_to(link_b)
        link_b.symlink_to(link_a)
    except OSError:
        pytest.skip("Symlink creation not permitted")

    patches = [{"subpath": "link_a", "patch_content": "+x\n", "base_checksum": "000"}]
    with pytest.raises(TacpSecurityError) as exc:
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


# SB-04: Symlink escape in 3rd item of batch
def test_sb04_symlink_escape_in_batch(sec_env: Dict[str, Any], tmp_path: Path) -> None:
    ws1 = sec_env["ws1"]
    f1 = ws1.root_path / "good1.txt"
    f2 = ws1.root_path / "good2.txt"
    f1.write_text("g1\n")
    f2.write_text("g2\n")

    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("outside\n")
    esc_link = ws1.root_path / "link_out.txt"
    try:
        esc_link.symlink_to(outside_file)
    except OSError:
        pytest.skip("Symlink creation not permitted")

    c1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    c2 = hashlib.sha256(f2.read_bytes()).hexdigest()
    c_out = hashlib.sha256(outside_file.read_bytes()).hexdigest()

    diff1 = "--- good1.txt\n+++ good1.txt\n@@ -1 +1 @@\n-g1\n+G1\n"
    diff2 = "--- good2.txt\n+++ good2.txt\n@@ -1 +1 @@\n-g2\n+G2\n"
    diff_out = "--- link_out.txt\n+++ link_out.txt\n@@ -1 +1 @@\n-outside\n+HACK\n"

    patches = [
        {"subpath": "good1.txt", "patch_content": diff1, "base_checksum": c1},
        {"subpath": "good2.txt", "patch_content": diff2, "base_checksum": c2},
        {"subpath": "link_out.txt", "patch_content": diff_out, "base_checksum": c_out},
    ]

    with pytest.raises(TacpSecurityError) as exc:
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=False)
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE
    # Invariant: Files 1 and 2 were NOT modified
    assert f1.read_text() == "g1\n"
    assert f2.read_text() == "g2\n"


# SB-05: Protected directory (.git/config) in batch
def test_sb05_protected_git_denied(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = [{"subpath": ".git/config", "patch_content": "+x\n", "base_checksum": "000"}]
    with pytest.raises(TacpSecurityError):
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)


# SB-06: Protected database (tacp.db) in batch
def test_sb06_protected_db_denied(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = [{"subpath": ".tacp/tacp.db", "patch_content": "+x\n", "base_checksum": "000"}]
    with pytest.raises(TacpSecurityError):
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)


# SB-07: Secret key file (id_rsa) in batch
def test_sb07_secret_key_denied(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = [{"subpath": "keys/id_rsa", "patch_content": "+x\n", "base_checksum": "000"}]
    with pytest.raises(TacpSecurityError):
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)


# SB-08: Secret env file (.env.production) in batch
def test_sb08_secret_env_denied(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = [{"subpath": ".env.production", "patch_content": "+x\n", "base_checksum": "000"}]
    with pytest.raises(TacpSecurityError):
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)


# SB-09: Path traversal (../../etc/passwd) in batch item
def test_sb09_path_traversal_denied(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = [{"subpath": "../../etc/passwd", "patch_content": "+x\n", "base_checksum": "000"}]
    with pytest.raises(TacpSecurityError):
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)


# SB-10: Absolute path escape (/etc/hosts) in batch item
def test_sb10_absolute_path_escape(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = [{"subpath": "/etc/hosts", "patch_content": "+x\n", "base_checksum": "000"}]
    with pytest.raises(TacpSecurityError):
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)


# SB-11: Empty batch rejection
def test_sb11_empty_batch_rejected(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    with pytest.raises(TacpValidationError) as exc:
        _approve_and_exec(sec_env, ws1.id, [], dry_run=True)
    assert "non-empty list" in str(exc.value)


# SB-12: Non-list batch payload rejection
def test_sb12_non_list_payload_rejected(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    with pytest.raises(TacpValidationError):
        sec_env["patch_service"].execute_patch_batch(workspace_id=ws1.id, patches="invalid_payload")


# SB-13: Missing subpath in item
def test_sb13_missing_subpath(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = [{"patch_content": "+x\n", "base_checksum": "abc"}]
    with pytest.raises(TacpValidationError) as exc:
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)
    assert "subpath parameter is required" in str(exc.value)


# SB-14: Missing patch_content in item
def test_sb14_missing_patch_content(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = [{"subpath": "a.txt", "base_checksum": "abc"}]
    with pytest.raises(TacpValidationError) as exc:
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)
    assert "patch_content parameter is required" in str(exc.value)


# SB-15: Missing base_checksum in item
def test_sb15_missing_base_checksum(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = [{"subpath": "a.txt", "patch_content": "+x\n"}]
    with pytest.raises(TacpValidationError) as exc:
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)
    assert "base_checksum parameter is required" in str(exc.value)


# SB-16: Null byte injection in subpath
def test_sb16_null_byte_subpath(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = [{"subpath": "test\0.txt", "patch_content": "+x\n", "base_checksum": "000"}]
    with pytest.raises((TacpValidationError, TacpSecurityError, ValueError)):
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)


# SB-17: Null byte injection in diff content
def test_sb17_null_byte_diff(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    f = ws1.root_path / "valid.txt"
    f.write_text("clean\n")
    c = hashlib.sha256(f.read_bytes()).hexdigest()
    patches = [
        {
            "subpath": "valid.txt",
            "patch_content": "--- a\n+++ a\n@@ -1 +1 @@\n-clean\n+bad\0\n",
            "base_checksum": c,
        }
    ]
    with pytest.raises(TacpValidationError) as exc:
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)
    assert "null byte" in str(exc.value).lower() or "binary" in str(exc.value).lower()


# SB-18: Binary payload injection in diff
def test_sb18_binary_payload_in_diff(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    f = ws1.root_path / "valid2.txt"
    f.write_text("clean\n")
    c = hashlib.sha256(f.read_bytes()).hexdigest()
    bad_diff = "--- a\n+++ a\n@@ -1 +1 @@\n-clean\n+\x00\x01\x02\x03\n"
    patches = [{"subpath": "valid2.txt", "patch_content": bad_diff, "base_checksum": c}]
    with pytest.raises(TacpValidationError):
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)


# SB-19: Excessive file count (> 10 files)
def test_sb19_excessive_file_count(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = [
        {"subpath": f"f{i}.txt", "patch_content": "+x\n", "base_checksum": "abc"} for i in range(11)
    ]
    with pytest.raises(TacpValidationError) as exc:
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)
    assert "exceeds maximum limit" in str(exc.value) or "exceeds limit" in str(exc.value)


# SB-20: Excessive diff size for single file (> 256 KB)
def test_sb20_excessive_diff_single_file(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    f = ws1.root_path / "big_diff.txt"
    f.write_text("initial\n")
    c = hashlib.sha256(f.read_bytes()).hexdigest()
    huge_diff = "--- a\n+++ a\n@@ -1 +1,2 @@\n initial\n+" + ("X" * 300000) + "\n"
    patches = [{"subpath": "big_diff.txt", "patch_content": huge_diff, "base_checksum": c}]
    with pytest.raises(TacpValidationError) as exc:
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)
    assert "exceeds limit" in str(exc.value)


# SB-21: Excessive aggregate diff size (> 1 MB)
def test_sb21_excessive_aggregate_diff(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = []
    # 5 files of 220KB diff each = 1.1 MB total diff (> 1 MB limit)
    chunk = "--- a\n+++ a\n@@ -1 +1,2 @@\n a\n+" + ("Z" * 220000) + "\n"
    for i in range(5):
        f = ws1.root_path / f"agg_{i}.txt"
        f.write_text("a\n")
        c = hashlib.sha256(f.read_bytes()).hexdigest()
        patches.append({"subpath": f"agg_{i}.txt", "patch_content": chunk, "base_checksum": c})

    with pytest.raises(TacpValidationError) as exc:
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=True)
    assert "Total batch patch diff size" in str(exc.value)


# SB-22: Excessive resulting single file size (> 2 MB)
def test_sb22_excessive_resulting_single_file(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    f = ws1.root_path / "res_big.txt"
    f.write_text("a\n")
    c = hashlib.sha256(f.read_bytes()).hexdigest()
    # Diff of 200KB repeated to produce large result
    diff = "--- a\n+++ a\n@@ -1 +1,2 @@\n a\n+" + ("M" * 250000) + "\n"
    patches = [{"subpath": "res_big.txt", "patch_content": diff, "base_checksum": c}]
    # We test with smaller limit in custom limits
    custom_limits = OutputLimits(max_resulting_file_bytes=1000)
    fs = FilesystemProvider(limits=custom_limits)
    with pytest.raises(TacpValidationError) as exc:
        fs.apply_patch_batch(ws1.root_path, patches, dry_run=True)
    assert "Resulting file size" in str(exc.value)


# SB-23: Excessive aggregate resulting size (> 5 MB)
def test_sb23_excessive_aggregate_resulting_size(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    f1 = ws1.root_path / "r1.txt"
    f2 = ws1.root_path / "r2.txt"
    f1.write_text("a\n")
    f2.write_text("b\n")
    c1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    c2 = hashlib.sha256(f2.read_bytes()).hexdigest()
    patches = [
        {
            "subpath": "r1.txt",
            "patch_content": "--- a\n+++ a\n@@ -1 +1,2 @@\n a\n+12345\n",
            "base_checksum": c1,
        },
        {
            "subpath": "r2.txt",
            "patch_content": "--- b\n+++ b\n@@ -1 +1,2 @@\n b\n+12345\n",
            "base_checksum": c2,
        },
    ]
    custom_limits = OutputLimits(max_batch_resulting_total_bytes=10)
    fs = FilesystemProvider(limits=custom_limits)
    with pytest.raises(TacpValidationError) as exc:
        fs.apply_patch_batch(ws1.root_path, patches, dry_run=True)
    assert "Total batch resulting size" in str(exc.value)


# SB-24: Lock deadlock stress test (concurrent reverse ordering)
def test_sb24_lock_deadlock_prevention(sec_env: Dict[str, Any]) -> None:
    lock_svc = sec_env["patch_service"].lock_service
    # Two resource sets in opposing order: hold_many MUST sort them internally
    set1 = ["ws-1:file_z.txt", "ws-1:file_a.txt"]
    set2 = ["ws-1:file_a.txt", "ws-1:file_z.txt"]

    with lock_svc.hold_many(set1, "owner-1"):
        # Since sorted, owner-1 acquired file_a first, then file_z
        with pytest.raises(TacpConflictError) as exc:
            with lock_svc.hold_many(set2, "owner-2"):
                pass
        assert "locked by 'owner-1'" in str(exc.value)


# SB-25: Concurrency collision during batch execution (OCC conflict on file 2)
def test_sb25_concurrency_collision_clean_abort(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    f1 = ws1.root_path / "col1.txt"
    f2 = ws1.root_path / "col2.txt"
    f1.write_text("orig1\n")
    f2.write_text("orig2\n")

    c1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    diff1 = "--- col1.txt\n+++ col1.txt\n@@ -1 +1 @@\n-orig1\n+NEW1\n"
    diff2 = "--- col2.txt\n+++ col2.txt\n@@ -1 +1 @@\n-orig2\n+NEW2\n"

    patches = [
        {"subpath": "col1.txt", "patch_content": diff1, "base_checksum": c1},
        {"subpath": "col2.txt", "patch_content": diff2, "base_checksum": "stale_hash"},
    ]
    with pytest.raises(TacpConflictError):
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=False)

    # Invariant: col1.txt must remain completely untouched
    assert f1.read_text() == "orig1\n"
    assert f2.read_text() == "orig2\n"


# SB-26: Atomic rollback on failure in staging phase
def test_sb26_atomic_rollback_staging_failure(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    f1 = ws1.root_path / "st1.txt"
    f2 = ws1.root_path / "st2.txt"
    f1.write_text("valid1\n")
    f2.write_text("valid2\n")

    c1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    c2 = hashlib.sha256(f2.read_bytes()).hexdigest()

    # File 2 has invalid hunk header format
    bad_diff = "--- st2.txt\n+++ st2.txt\nnot a hunk header\n"
    patches = [
        {
            "subpath": "st1.txt",
            "patch_content": "--- st1.txt\n+++ st1.txt\n@@ -1 +1 @@\n-valid1\n+mod1\n",
            "base_checksum": c1,
        },
        {"subpath": "st2.txt", "patch_content": bad_diff, "base_checksum": c2},
    ]

    with pytest.raises(TacpValidationError):
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=False)

    assert f1.read_text() == "valid1\n"
    assert f2.read_text() == "valid2\n"


# SB-27: Atomic rollback on failure during commit phase
def test_sb27_atomic_rollback_commit_failure(
    sec_env: Dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    ws1 = sec_env["ws1"]
    f1 = ws1.root_path / "cm1.txt"
    f2 = ws1.root_path / "cm2.txt"
    f1.write_text("start 1\n")
    f2.write_text("start 2\n")

    c1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    c2 = hashlib.sha256(f2.read_bytes()).hexdigest()

    diff1 = "--- cm1.txt\n+++ cm1.txt\n@@ -1 +1 @@\n-start 1\n+mutated 1\n"
    diff2 = "--- cm2.txt\n+++ cm2.txt\n@@ -1 +1 @@\n-start 2\n+mutated 2\n"
    patches = [
        {"subpath": "cm1.txt", "patch_content": diff1, "base_checksum": c1},
        {"subpath": "cm2.txt", "patch_content": diff2, "base_checksum": c2},
    ]

    # Monkeypatch os.replace on second file (simulating commit failure)
    orig_replace = os.replace
    call_count = 0

    def mock_replace(src: Any, dst: Any) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("Injected disk commit failure")
        orig_replace(src, dst)

    monkeypatch.setattr(os, "replace", mock_replace)

    with pytest.raises(TacpSecurityError) as exc:
        _approve_and_exec(sec_env, ws1.id, patches, dry_run=False)
    assert "Batch commit failed; all modified files rolled back" in str(exc.value)

    # Invariant: File 1 was initially committed, then automatically restored!
    assert f1.read_text() == "start 1\n"
    assert f2.read_text() == "start 2\n"


# SB-28: Stale approval token reuse rejection
def test_sb28_stale_approval_token_reuse(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    f = ws1.root_path / "reuse.txt"
    f.write_text("line\n")
    c = hashlib.sha256(f.read_bytes()).hexdigest()
    diff = "--- reuse.txt\n+++ reuse.txt\n@@ -1 +1 @@\n-line\n+next\n"
    patches = [{"subpath": "reuse.txt", "patch_content": diff, "base_checksum": c}]

    ae = sec_env["approval_engine"]
    ps = sec_env["patch_service"]
    b_hash = compute_canonical_batch_hash(patches)
    ticket = ae.create_ticket("agent", "workspace.patch_batch", ws1.id, "*", b_hash)
    ae.approve(ticket.token)

    # First use: success
    res = ps.execute_patch_batch(
        ws1.id, patches, dry_run=False, approval_token=ticket.token, principal_id="agent"
    )
    assert res.status == PatchStatus.APPLIED

    # Second use with same token: rejected
    with pytest.raises(TacpSecurityError) as exc:
        ps.execute_patch_batch(
            ws1.id, patches, dry_run=False, approval_token=ticket.token, principal_id="agent"
        )
    assert exc.value.code == ErrorCode.APPROVAL_ALREADY_USED


# SB-29: Expired approval token rejection
def test_sb29_expired_approval_token(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = [{"subpath": "a.txt", "patch_content": "+a\n", "base_checksum": "abc"}]
    ae = sec_env["approval_engine"]
    b_hash = compute_canonical_batch_hash(patches)
    # Create with negative TTL (already expired)
    ticket = ae.create_ticket(
        "agent", "workspace.patch_batch", ws1.id, "*", b_hash, ttl_seconds=-10
    )

    with pytest.raises(TacpSecurityError) as exc:
        ae.approve(ticket.token)
    assert exc.value.code == ErrorCode.APPROVAL_EXPIRED


# SB-30: Approval hash mismatch rejection
def test_sb30_approval_hash_mismatch(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    f = ws1.root_path / "mismatch.txt"
    f.write_text("orig\n")
    c = hashlib.sha256(f.read_bytes()).hexdigest()

    orig_patches = [
        {
            "subpath": "mismatch.txt",
            "patch_content": "--- a\n+++ a\n@@ -1 +1 @@\n-orig\n+A\n",
            "base_checksum": c,
        }
    ]
    ae = sec_env["approval_engine"]
    ps = sec_env["patch_service"]
    b_hash = compute_canonical_batch_hash(orig_patches)
    ticket = ae.create_ticket("agent", "workspace.patch_batch", ws1.id, "*", b_hash)
    ae.approve(ticket.token)

    # Agent modifies diff payload after approval
    tampered_patches = [
        {
            "subpath": "mismatch.txt",
            "patch_content": "--- a\n+++ a\n@@ -1 +1 @@\n-orig\n+MALICIOUS\n",
            "base_checksum": c,
        }
    ]
    with pytest.raises(TacpSecurityError) as exc:
        ps.execute_patch_batch(
            ws1.id,
            tampered_patches,
            dry_run=False,
            approval_token=ticket.token,
            principal_id="agent",
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED


# SB-31: Approval workspace mismatch rejection
def test_sb31_approval_workspace_mismatch(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    ws2 = sec_env["ws2"]
    patches = [{"subpath": "a.txt", "patch_content": "+a\n", "base_checksum": "abc"}]
    ae = sec_env["approval_engine"]
    b_hash = compute_canonical_batch_hash(patches)
    ticket = ae.create_ticket("agent", "workspace.patch_batch", ws1.id, "*", b_hash)
    ae.approve(ticket.token)

    # Attempt to consume in ws2
    with pytest.raises(TacpSecurityError) as exc:
        ae.verify_and_consume(ticket.token, "agent", "workspace.patch_batch", ws2.id, "*", b_hash)
    assert "Approval workspace mismatch" in exc.value.message


# SB-32: Approval target mismatch rejection
def test_sb32_approval_target_mismatch(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = [{"subpath": "a.txt", "patch_content": "+a\n", "base_checksum": "abc"}]
    ae = sec_env["approval_engine"]
    b_hash = compute_canonical_batch_hash(patches)
    ticket = ae.create_ticket("agent", "workspace.patch_batch", ws1.id, "exact/target.txt", b_hash)
    ae.approve(ticket.token)

    with pytest.raises(TacpSecurityError) as exc:
        ae.verify_and_consume(
            ticket.token, "agent", "workspace.patch_batch", ws1.id, "other/target.txt", b_hash
        )
    assert "Approval target path mismatch" in exc.value.message


# SB-33: Approval caller/principal spoofing rejection
def test_sb33_approval_principal_spoofing(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = [{"subpath": "a.txt", "patch_content": "+a\n", "base_checksum": "abc"}]
    ae = sec_env["approval_engine"]
    b_hash = compute_canonical_batch_hash(patches)
    ticket = ae.create_ticket("authorized-agent", "workspace.patch_batch", ws1.id, "*", b_hash)
    ae.approve(ticket.token)

    with pytest.raises(TacpSecurityError) as exc:
        ae.verify_and_consume(
            ticket.token, "attacker-agent", "workspace.patch_batch", ws1.id, "*", b_hash
        )
    assert "Approval principal mismatch" in exc.value.message


# SB-34: Double-spend approval ticket race
def test_sb34_double_spend_race(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    patches = [{"subpath": "a.txt", "patch_content": "+a\n", "base_checksum": "abc"}]
    ae = sec_env["approval_engine"]
    b_hash = compute_canonical_batch_hash(patches)
    ticket = ae.create_ticket("agent", "workspace.patch_batch", ws1.id, "*", b_hash)
    ae.approve(ticket.token)

    # First consumption
    assert (
        ae.verify_and_consume(ticket.token, "agent", "workspace.patch_batch", ws1.id, "*", b_hash)
        is True
    )
    # Immediate second consumption
    with pytest.raises(TacpSecurityError) as exc:
        ae.verify_and_consume(ticket.token, "agent", "workspace.patch_batch", ws1.id, "*", b_hash)
    assert exc.value.code == ErrorCode.APPROVAL_ALREADY_USED


# SB-35: Batch rollback already rolled back rejection
def test_sb35_rollback_already_rolled_back(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    f = ws1.root_path / "rb_repeat.txt"
    f.write_text("orig\n")
    c = hashlib.sha256(f.read_bytes()).hexdigest()
    diff = "--- rb_repeat.txt\n+++ rb_repeat.txt\n@@ -1 +1 @@\n-orig\n+mut\n"
    res = _approve_and_exec(
        sec_env, ws1.id, [{"subpath": "rb_repeat.txt", "patch_content": diff, "base_checksum": c}]
    )

    sec_env["patch_service"].rollback_batch(res.batch_id)
    with pytest.raises(TacpConflictError) as exc:
        sec_env["patch_service"].rollback_batch(res.batch_id)
    assert "already been rolled back" in str(exc.value)


# SB-36: Batch rollback non-existent ID rejection
def test_sb36_rollback_nonexistent_id(sec_env: Dict[str, Any]) -> None:
    with pytest.raises(TacpNotFoundError) as exc:
        sec_env["patch_service"].rollback_batch("batch-nonexistent-12345")
    assert "not found" in str(exc.value).lower()


# SB-37: Batch rollback with disk drift / checksum conflict
def test_sb37_rollback_disk_drift_conflict(sec_env: Dict[str, Any]) -> None:
    ws1 = sec_env["ws1"]
    f = ws1.root_path / "drift.txt"
    f.write_text("v1\n")
    c = hashlib.sha256(f.read_bytes()).hexdigest()
    diff = "--- drift.txt\n+++ drift.txt\n@@ -1 +1 @@\n-v1\n+v2\n"
    res = _approve_and_exec(
        sec_env, ws1.id, [{"subpath": "drift.txt", "patch_content": diff, "base_checksum": c}]
    )

    # External actor modifies file on disk after batch was applied
    f.write_text("v3_tampered\n")

    with pytest.raises(TacpConflictError) as exc:
        sec_env["patch_service"].rollback_batch(res.batch_id)
    assert "Rollback conflict" in str(exc.value)


# SB-38: Dual flag enforcement: mutation_enabled=False, batch_mutation_enabled=True -> Deny
def test_sb38_dual_flag_mutation_disabled(sec_env: Dict[str, Any]) -> None:
    pe = PolicyEngine(mutation_enabled=False, batch_mutation_enabled=True)
    from tacp.control.identity import Principal, RequestContext

    ctx = RequestContext(capability="workspace.patch_batch", principal=Principal(id="agent"))
    decision = pe.evaluate_request(ctx, workspace=sec_env["ws1"])
    assert decision.allowed is False
    assert "mutation is disabled" in decision.reason


# SB-39: Dual flag enforcement: mutation_enabled=True, batch_mutation_enabled=False -> Deny batch
def test_sb39_dual_flag_batch_disabled(sec_env: Dict[str, Any]) -> None:
    pe = PolicyEngine(mutation_enabled=True, batch_mutation_enabled=False)
    from tacp.control.identity import Principal, RequestContext

    ctx = RequestContext(capability="workspace.patch_batch", principal=Principal(id="agent"))
    decision = pe.evaluate_request(ctx, workspace=sec_env["ws1"])
    assert decision.allowed is False
    assert "batch mutation is disabled" in decision.reason


# SB-40: Read-only negative API audit on batch code
def test_sb40_negative_api_audit_batch() -> None:
    import inspect

    from tacp.core.patch_service import PatchService
    from tacp.providers.filesystem import FilesystemProvider

    batch_src = inspect.getsource(PatchService.execute_patch_batch)
    batch_rb_src = inspect.getsource(PatchService.rollback_batch)
    fs_batch_src = inspect.getsource(FilesystemProvider.apply_patch_batch)
    fs_rb_src = inspect.getsource(FilesystemProvider.rollback_patch_batch)

    combined = batch_src + batch_rb_src + fs_batch_src + fs_rb_src
    for dangerous in [
        "subprocess",
        "os.system",
        "popen",
        "shell=True",
        "chmod",
        "chown",
        "shutil.rmtree",
    ]:
        assert dangerous not in combined.lower()
