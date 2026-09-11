"""30 Security attack cases for TACP Phase 2 Gate B Slice 1 (workspace.patch).

Verifies strict fail-closed security invariants, jailing, policy hierarchy,
optimistic concurrency control, and scoped approval enforcement.
"""

import hashlib
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest

from tacp.control.approval import ApprovalEngine
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.lock_service import LockService
from tacp.core.patch_service import PatchService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import (
    ErrorCode,
    TacpApprovalRequiredError,
    TacpConflictError,
    TacpNotFoundError,
    TacpSecurityError,
    TacpValidationError,
)
from tacp.infrastructure.config import OutputLimits, TacpConfig
from tacp.infrastructure.database import Database
from tacp.providers.filesystem import FilesystemProvider


@pytest.fixture
def sec_env(test_db: Database, tmp_path: Path) -> Dict[str, Any]:
    ws_dir = tmp_path / "sec_ws"
    ws_dir.mkdir()
    (ws_dir / "src").mkdir()
    sample = ws_dir / "src" / "target.py"
    sample.write_text("print('safe')\n")

    limits = OutputLimits(
        max_patch_bytes=1024,
        max_file_size_bytes=2048,
        max_resulting_file_bytes=4096,
    )
    cfg = TacpConfig(
        data_dir=tmp_path / ".tacp",
        db_path=test_db.db_path,
        mutation_enabled=True,
        read_only=False,
        limits=limits,
    )

    ws_service = WorkspaceService(test_db)
    ws = ws_service.register_workspace("sec_proj", ws_dir)

    policy_engine = PolicyEngine(mutation_enabled=True, read_only_enforced=False)
    audit_service = AuditService(test_db)
    fs_provider = FilesystemProvider(limits=limits)
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
        "service": patch_service,
        "appr_engine": approval_engine,
        "ws": ws,
        "ws_dir": ws_dir,
        "target": sample,
        "policy_engine": policy_engine,
        "db": test_db,
    }


def make_valid_patch(target: Path, new_line: str = "print('patched')\n") -> Tuple[str, str, str]:
    base_hash = hashlib.sha256(target.read_bytes()).hexdigest()
    diff = f"--- a/{target.name}\n+++ b/{target.name}\n@@ -1,1 +1,1 @@\n-print('safe')\n+{new_line}"
    diff_hash = hashlib.sha256(diff.encode("utf-8")).hexdigest()
    return diff, base_hash, diff_hash


# Case 1: Escape workspace root via .. in subpath
def test_sec_case_01_path_traversal_double_dot(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    diff, base_hash, _ = make_valid_patch(sec_env["target"])
    with pytest.raises(TacpSecurityError):
        svc.execute_patch(ws.id, "../escape.py", diff, base_hash, dry_run=True)


# Case 2: Null-byte injection in subpath
def test_sec_case_02_null_byte_in_subpath(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    diff, base_hash, _ = make_valid_patch(sec_env["target"])
    with pytest.raises(TacpSecurityError) as exc:
        svc.execute_patch(ws.id, "src/target.py\0.js", diff, base_hash, dry_run=True)
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


# Case 3: Absolute path injection (/etc/passwd)
def test_sec_case_03_absolute_path_injection(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    diff, base_hash, _ = make_valid_patch(sec_env["target"])
    with pytest.raises(TacpSecurityError) as exc:
        svc.execute_patch(ws.id, "/etc/passwd", diff, base_hash, dry_run=True)
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


# Case 4: Symlink traversal outside workspace root
def test_sec_case_04_symlink_traversal_outside(sec_env: Dict[str, Any], tmp_path: Path) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    ws_dir = sec_env["ws_dir"]
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("sensitive outside data\n")

    symlink = ws_dir / "src" / "sym_outside.py"
    try:
        symlink.symlink_to(outside_file)
    except OSError:
        pytest.skip("Symlink creation not supported in this environment")

    diff, base_hash, _ = make_valid_patch(sec_env["target"])
    with pytest.raises(TacpSecurityError) as exc:
        svc.execute_patch(ws.id, "src/sym_outside.py", diff, base_hash, dry_run=True)
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


# Case 5: Symlink target mutation (patching symlink pointing inside)
def test_sec_case_05_symlink_mutation_forbidden(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    ws_dir = sec_env["ws_dir"]
    target = sec_env["target"]
    symlink = ws_dir / "src" / "sym_inside.py"
    try:
        symlink.symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation not supported in this environment")

    diff, base_hash, _ = make_valid_patch(target)
    with pytest.raises(TacpSecurityError) as exc:
        svc.execute_patch(ws.id, "src/sym_inside.py", diff, base_hash, dry_run=True)
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


# Case 6: Direct patch to .git/config
def test_sec_case_06_patch_git_config_forbidden(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    ws_dir = sec_env["ws_dir"]
    (ws_dir / ".git").mkdir(exist_ok=True)
    git_cfg = ws_dir / ".git" / "config"
    git_cfg.write_text("[core]\n\trepositoryformatversion = 0\n")
    base_hash = hashlib.sha256(git_cfg.read_bytes()).hexdigest()

    diff = "--- a/config\n+++ b/config\n@@ -1,2 +1,2 @@\n-[core]\n+[pwn]\n"
    with pytest.raises(TacpSecurityError) as exc:
        svc.execute_patch(ws.id, ".git/config", diff, base_hash, dry_run=True)
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED


# Case 7: Direct patch to .git/HEAD
def test_sec_case_07_patch_git_head_forbidden(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    diff, base_hash, _ = make_valid_patch(sec_env["target"])
    with pytest.raises(TacpSecurityError):
        svc.execute_patch(ws.id, ".git/HEAD", diff, base_hash, dry_run=True)


# Case 8: Direct patch to .tacp/tacp.db
def test_sec_case_08_patch_tacp_db_forbidden(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    diff, base_hash, _ = make_valid_patch(sec_env["target"])
    with pytest.raises(TacpSecurityError):
        svc.execute_patch(ws.id, ".tacp/tacp.db", diff, base_hash, dry_run=True)


# Case 9: Direct patch to .env
def test_sec_case_09_patch_env_forbidden(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    ws_dir = sec_env["ws_dir"]
    env_file = ws_dir / ".env"
    env_file.write_text("SECRET=123\n")
    base_hash = hashlib.sha256(env_file.read_bytes()).hexdigest()
    diff = "--- a/.env\n+++ b/.env\n@@ -1,1 +1,1 @@\n-SECRET=123\n+SECRET=pwned\n"
    with pytest.raises(TacpSecurityError):
        svc.execute_patch(ws.id, ".env", diff, base_hash, dry_run=True)


# Case 10: Direct patch to .env.local
def test_sec_case_10_patch_env_local_forbidden(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    diff, base_hash, _ = make_valid_patch(sec_env["target"])
    with pytest.raises(TacpSecurityError):
        svc.execute_patch(ws.id, ".env.local", diff, base_hash, dry_run=True)


# Case 11: Direct patch to id_rsa / id_ed25519
def test_sec_case_11_patch_ssh_keys_forbidden(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    diff, base_hash, _ = make_valid_patch(sec_env["target"])
    with pytest.raises(TacpSecurityError):
        svc.execute_patch(ws.id, "keys/id_rsa", diff, base_hash, dry_run=True)
    with pytest.raises(TacpSecurityError):
        svc.execute_patch(ws.id, "keys/id_ed25519", diff, base_hash, dry_run=True)


# Case 12: Direct patch to .key / .pem
def test_sec_case_12_patch_key_pem_forbidden(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    ws_dir = sec_env["ws_dir"]
    key_file = ws_dir / "server.key"
    key_file.write_text("cert key content\n")
    base_hash = hashlib.sha256(key_file.read_bytes()).hexdigest()
    diff = "--- a/server.key\n+++ b/server.key\n@@ -1,1 +1,1 @@\n-cert key content\n+pwned\n"
    with pytest.raises(TacpSecurityError):
        svc.execute_patch(ws.id, "server.key", diff, base_hash, dry_run=False)


# Case 13: Mutation when mutation_enabled = false
def test_sec_case_13_mutation_disabled(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    diff, base_hash, _ = make_valid_patch(sec_env["target"])
    # Temporarily set policy_engine mutation_enabled to False
    svc.policy_engine.mutation_enabled = False
    try:
        with pytest.raises(TacpSecurityError) as exc:
            svc.execute_patch(ws.id, "src/target.py", diff, base_hash, dry_run=True)
        assert "mutation is disabled" in str(exc.value)
    finally:
        svc.policy_engine.mutation_enabled = True


# Case 14: Mutation when workspace is SUSPENDED
def test_sec_case_14_suspended_workspace(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    diff, base_hash, _ = make_valid_patch(sec_env["target"])
    # Suspend workspace in DB
    conn = svc.db.connect()
    conn.execute("UPDATE workspaces SET status = 'SUSPENDED' WHERE id = ?;", (ws.id,))
    conn.commit()
    try:
        with pytest.raises(TacpSecurityError) as exc:
            svc.execute_patch(ws.id, "src/target.py", diff, base_hash, dry_run=True)
        assert "not ACTIVE" in str(exc.value)
    finally:
        conn.execute("UPDATE workspaces SET status = 'ACTIVE' WHERE id = ?;", (ws.id,))
        conn.commit()


# Case 15: Mutation when workspace is non-existent
def test_sec_case_15_nonexistent_workspace(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    diff, base_hash, _ = make_valid_patch(sec_env["target"])
    with pytest.raises(TacpNotFoundError):
        svc.execute_patch("nonexistent-ws-id", "src/target.py", diff, base_hash, dry_run=True)


# Case 16: Mutation with missing approval token (non-dry-run)
def test_sec_case_16_missing_approval_token(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    diff, base_hash, _ = make_valid_patch(sec_env["target"])
    with pytest.raises(TacpApprovalRequiredError):
        svc.execute_patch(
            ws.id, "src/target.py", diff, base_hash, dry_run=False, approval_token=None
        )


# Case 17: Mutation with invalid/fake approval token
def test_sec_case_17_invalid_approval_token(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    diff, base_hash, _ = make_valid_patch(sec_env["target"])
    with pytest.raises(TacpSecurityError) as exc:
        svc.execute_patch(
            ws.id,
            "src/target.py",
            diff,
            base_hash,
            dry_run=False,
            approval_token="fake_token_123",  # noqa: S106
        )
    assert exc.value.code in (ErrorCode.APPROVAL_REQUIRED, ErrorCode.NOT_AUTHORIZED)


# Case 18: Mutation with expired approval token
def test_sec_case_18_expired_approval_token(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    appr = sec_env["appr_engine"]
    ws = sec_env["ws"]
    diff, base_hash, diff_hash = make_valid_patch(sec_env["target"])

    ticket = appr.create_ticket(
        principal_id="agent",
        action_type="workspace.patch",
        workspace_id=ws.id,
        target_path="src/target.py",
        patch_hash=diff_hash,
        ttl_seconds=-5,
    )
    conn = svc.db.connect()
    conn.execute("UPDATE approvals SET status = 'APPROVED' WHERE token = ?;", (ticket.token,))
    conn.commit()

    with pytest.raises(TacpSecurityError) as exc:
        svc.execute_patch(
            ws.id, "src/target.py", diff, base_hash, dry_run=False, approval_token=ticket.token
        )
    assert exc.value.code == ErrorCode.APPROVAL_EXPIRED


# Case 19: Replay attack (already consumed approval token)
def test_sec_case_19_replay_consumed_token(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    appr = sec_env["appr_engine"]
    ws = sec_env["ws"]
    diff, base_hash, diff_hash = make_valid_patch(sec_env["target"])

    ticket = appr.create_ticket("agent", "workspace.patch", ws.id, "src/target.py", diff_hash)
    appr.approve(ticket.token)

    # First execution succeeds
    svc.execute_patch(
        ws.id, "src/target.py", diff, base_hash, dry_run=False, approval_token=ticket.token
    )

    # Second execution using same token must fail
    with pytest.raises(TacpSecurityError) as exc:
        svc.execute_patch(
            ws.id, "src/target.py", diff, base_hash, dry_run=False, approval_token=ticket.token
        )
    assert exc.value.code == ErrorCode.APPROVAL_ALREADY_USED


# Case 20: Approval token for different workspace
def test_sec_case_20_approval_foreign_workspace(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    appr = sec_env["appr_engine"]
    ws = sec_env["ws"]
    diff, base_hash, diff_hash = make_valid_patch(sec_env["target"])

    ticket = appr.create_ticket(
        "agent", "workspace.patch", "foreign_ws_id", "src/target.py", diff_hash
    )
    appr.approve(ticket.token)

    with pytest.raises(TacpSecurityError) as exc:
        svc.execute_patch(
            ws.id, "src/target.py", diff, base_hash, dry_run=False, approval_token=ticket.token
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED


# Case 21: Approval token for different target file
def test_sec_case_21_approval_foreign_target_path(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    appr = sec_env["appr_engine"]
    ws = sec_env["ws"]
    diff, base_hash, diff_hash = make_valid_patch(sec_env["target"])

    ticket = appr.create_ticket("agent", "workspace.patch", ws.id, "src/other.py", diff_hash)
    appr.approve(ticket.token)

    with pytest.raises(TacpSecurityError) as exc:
        svc.execute_patch(
            ws.id, "src/target.py", diff, base_hash, dry_run=False, approval_token=ticket.token
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED


# Case 22: Approval token for different patch hash
def test_sec_case_22_approval_patch_hash_mismatch(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    appr = sec_env["appr_engine"]
    ws = sec_env["ws"]
    diff, base_hash, _ = make_valid_patch(sec_env["target"])

    ticket = appr.create_ticket(
        "agent", "workspace.patch", ws.id, "src/target.py", "foreign_hash_value"
    )
    appr.approve(ticket.token)

    with pytest.raises(TacpSecurityError) as exc:
        svc.execute_patch(
            ws.id, "src/target.py", diff, base_hash, dry_run=False, approval_token=ticket.token
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED


# Case 23: Approval token for different principal
def test_sec_case_23_approval_principal_mismatch(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    appr = sec_env["appr_engine"]
    ws = sec_env["ws"]
    diff, base_hash, diff_hash = make_valid_patch(sec_env["target"])

    ticket = appr.create_ticket("legit_agent", "workspace.patch", ws.id, "src/target.py", diff_hash)
    appr.approve(ticket.token)

    with pytest.raises(TacpSecurityError) as exc:
        svc.execute_patch(
            ws.id,
            "src/target.py",
            diff,
            base_hash,
            dry_run=False,
            approval_token=ticket.token,
            principal_id="attacker_agent",
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED


# Case 24: Base checksum mismatch
def test_sec_case_24_base_checksum_conflict(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    diff, _, _ = make_valid_patch(sec_env["target"])
    with pytest.raises(TacpConflictError):
        svc.execute_patch(ws.id, "src/target.py", diff, "bad_checksum_hash", dry_run=True)


# Case 25: Patch diff exceeding size limit (max_patch_bytes)
def test_sec_case_25_patch_diff_size_exceeded(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    _, base_hash, _ = make_valid_patch(sec_env["target"])
    huge_diff = "A" * (svc.config.limits.max_patch_bytes + 500)
    with pytest.raises(TacpValidationError) as exc:
        svc.execute_patch(ws.id, "src/target.py", huge_diff, base_hash, dry_run=True)
    assert "exceeds limit" in str(exc.value)


# Case 26: Target file exceeding editable limit (max_file_size_bytes)
def test_sec_case_26_target_file_size_exceeded(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    ws_dir = sec_env["ws_dir"]
    large_file = ws_dir / "src" / "large.txt"
    large_file.write_text("X" * (svc.config.limits.max_file_size_bytes + 500))
    base_hash = hashlib.sha256(large_file.read_bytes()).hexdigest()

    diff = "--- a/large.txt\n+++ b/large.txt\n@@ -1,1 +1,1 @@\n-X\n+Y\n"
    with pytest.raises(TacpValidationError) as exc:
        svc.execute_patch(ws.id, "src/large.txt", diff, base_hash, dry_run=True)
    assert "exceeds limit" in str(exc.value)


# Case 27: Resulting file exceeding size limit (max_resulting_file_bytes)
def test_sec_case_27_resulting_file_size_exceeded(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    target = sec_env["target"]
    base_hash = hashlib.sha256(target.read_bytes()).hexdigest()

    # Diff that injects 5000 characters
    injected = "Z" * 5000 + "\n"
    diff = f"--- a/target.py\n+++ b/target.py\n@@ -1,1 +1,2 @@\n print('safe')\n+{injected}"
    with pytest.raises(TacpValidationError) as exc:
        svc.execute_patch(ws.id, "src/target.py", diff, base_hash, dry_run=True)
    assert "exceeds limit" in str(exc.value)


# Case 28: Binary file patching (null bytes in source)
def test_sec_case_28_binary_source_file_rejected(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    ws_dir = sec_env["ws_dir"]
    bin_file = ws_dir / "src" / "data.bin"
    bin_file.write_bytes(b"\x7fELF\x00\x00\x00\x00")
    base_hash = hashlib.sha256(bin_file.read_bytes()).hexdigest()

    diff = "--- a/data.bin\n+++ b/data.bin\n@@ -1,1 +1,1 @@\n-a\n+b\n"
    with pytest.raises(TacpValidationError) as exc:
        svc.execute_patch(ws.id, "src/data.bin", diff, base_hash, dry_run=True)
    assert "Binary files" in str(exc.value)


# Case 29: Null byte in patch content
def test_sec_case_29_null_byte_in_patch_content(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    target = sec_env["target"]
    base_hash = hashlib.sha256(target.read_bytes()).hexdigest()

    diff = (
        "--- a/target.py\n"
        "+++ b/target.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-print('safe')\n"
        "+print('pwned\0payload')\n"
    )
    with pytest.raises(TacpValidationError) as exc:
        svc.execute_patch(ws.id, "src/target.py", diff, base_hash, dry_run=True)
    assert "null bytes" in str(exc.value).lower()


# Case 30: Concurrent lock conflict
def test_sec_case_30_concurrent_lock_conflict(sec_env: Dict[str, Any]) -> None:
    svc = sec_env["service"]
    ws = sec_env["ws"]
    diff, base_hash, _ = make_valid_patch(sec_env["target"])

    # Simulate another transaction holding the lock
    resource_id = f"{ws.id}:src/target.py"
    token = svc.lock_service.acquire_lock(resource_id, "foreign_writer", ttl_seconds=30)
    try:
        with pytest.raises(TacpConflictError) as exc:
            svc.execute_patch(ws.id, "src/target.py", diff, base_hash, dry_run=True)
        assert "locked by" in str(exc.value)
    finally:
        svc.lock_service.release_lock(resource_id, token)
