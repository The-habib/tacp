"""Unit tests for FilesystemProvider patch and atomic replacement (Category M & D)."""

import hashlib
from pathlib import Path

import pytest

from tacp.domain.errors import (
    ErrorCode,
    TacpConflictError,
    TacpNotFoundError,
    TacpSecurityError,
    TacpValidationError,
)
from tacp.domain.patch import PatchStatus
from tacp.infrastructure.config import OutputLimits
from tacp.providers.filesystem import FilesystemProvider


@pytest.fixture
def provider() -> FilesystemProvider:
    limits = OutputLimits(
        max_patch_bytes=10240,
        max_file_size_bytes=51200,
        max_resulting_file_bytes=102400,
    )
    return FilesystemProvider(limits=limits)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "src").mkdir()
    (ws / "src" / "sample.py").write_text("def hello():\n    return 42\n")
    return ws


def test_single_hunk_patch_application(provider: FilesystemProvider, workspace: Path) -> None:
    target = workspace / "src" / "sample.py"
    orig_bytes = target.read_bytes()
    base_checksum = hashlib.sha256(orig_bytes).hexdigest()

    diff = (
        "--- a/src/sample.py\n"
        "+++ b/src/sample.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def hello():\n"
        "-    return 42\n"
        "+    return 100\n"
    )

    res = provider.apply_patch(
        workspace_root=workspace,
        subpath="src/sample.py",
        patch_diff=diff,
        base_checksum=base_checksum,
        dry_run=False,
    )
    assert res["status"] == PatchStatus.APPLIED
    assert res["lines_added"] == 1
    assert res["lines_removed"] == 1
    assert target.read_text() == "def hello():\n    return 100\n"
    assert res["snapshot_path"] is not None
    assert Path(res["snapshot_path"]).exists()


def test_dry_run_does_not_modify_file(provider: FilesystemProvider, workspace: Path) -> None:
    target = workspace / "src" / "sample.py"
    orig_text = target.read_text()
    base_checksum = hashlib.sha256(target.read_bytes()).hexdigest()

    diff = (
        "--- a/src/sample.py\n"
        "+++ b/src/sample.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def hello():\n"
        "-    return 42\n"
        "+    return 100\n"
    )

    res = provider.apply_patch(
        workspace_root=workspace,
        subpath="src/sample.py",
        patch_diff=diff,
        base_checksum=base_checksum,
        dry_run=True,
    )
    assert res["status"] == PatchStatus.SIMULATED
    assert res["snapshot_path"] is None
    # Disk file remains completely unchanged
    assert target.read_text() == orig_text


def test_multi_hunk_patch(provider: FilesystemProvider, workspace: Path) -> None:
    target = workspace / "src" / "multi.py"
    lines = [f"line {i}" for i in range(20)]
    target.write_text("\n".join(lines) + "\n")
    base_checksum = hashlib.sha256(target.read_bytes()).hexdigest()

    diff = (
        "--- a/src/multi.py\n"
        "+++ b/src/multi.py\n"
        "@@ -1,4 +1,4 @@\n"
        " line 0\n"
        "-line 1\n"
        "+line 1 changed\n"
        " line 2\n"
        " line 3\n"
        "@@ -10,4 +10,4 @@\n"
        " line 9\n"
        "-line 10\n"
        "+line 10 changed\n"
        " line 11\n"
        " line 12\n"
    )

    res = provider.apply_patch(
        workspace_root=workspace,
        subpath="src/multi.py",
        patch_diff=diff,
        base_checksum=base_checksum,
        dry_run=False,
    )
    assert res["status"] == PatchStatus.APPLIED
    assert res["lines_added"] == 2
    assert res["lines_removed"] == 2

    content = target.read_text()
    assert "line 1 changed" in content
    assert "line 10 changed" in content


def test_hunk_context_mismatch_fails(provider: FilesystemProvider, workspace: Path) -> None:
    target = workspace / "src" / "sample.py"
    base_checksum = hashlib.sha256(target.read_bytes()).hexdigest()

    # Wrong context: says "def wrong_context():" instead of "def hello():"
    bad_diff = (
        "--- a/src/sample.py\n"
        "+++ b/src/sample.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def wrong_context():\n"
        "-    return 42\n"
        "+    return 100\n"
    )

    with pytest.raises(TacpValidationError) as exc:
        provider.apply_patch(
            workspace_root=workspace,
            subpath="src/sample.py",
            patch_diff=bad_diff,
            base_checksum=base_checksum,
            dry_run=False,
        )
    assert "Hunk mismatch" in str(exc.value)
    # Target file remained untouched
    assert target.read_text() == "def hello():\n    return 42\n"


def test_base_checksum_conflict_fails(provider: FilesystemProvider, workspace: Path) -> None:
    diff = (
        "--- a/src/sample.py\n"
        "+++ b/src/sample.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def hello():\n"
        "-    return 42\n"
        "+    return 100\n"
    )

    with pytest.raises(TacpConflictError) as exc:
        provider.apply_patch(
            workspace_root=workspace,
            subpath="src/sample.py",
            patch_diff=diff,
            base_checksum="0000000000000000000000000000000000000000000000000000000000000000",
            dry_run=False,
        )
    assert "Base checksum mismatch" in str(exc.value)


def test_patch_directory_fails(provider: FilesystemProvider, workspace: Path) -> None:
    with pytest.raises(TacpValidationError) as exc:
        provider.apply_patch(
            workspace_root=workspace,
            subpath="src",
            patch_diff="diff",
            base_checksum="abc",
            dry_run=False,
        )
    assert "is a directory" in str(exc.value)


def test_patch_nonexistent_fails(provider: FilesystemProvider, workspace: Path) -> None:
    with pytest.raises(TacpNotFoundError) as exc:
        provider.apply_patch(
            workspace_root=workspace,
            subpath="src/nonexistent.py",
            patch_diff="diff",
            base_checksum="abc",
            dry_run=False,
        )
    assert "does not exist" in str(exc.value)


def test_patch_secret_file_denied(provider: FilesystemProvider, workspace: Path) -> None:
    secret = workspace / ".env"
    secret.write_text("API_KEY=secret123\n")
    base_checksum = hashlib.sha256(secret.read_bytes()).hexdigest()

    with pytest.raises(TacpSecurityError) as exc:
        provider.apply_patch(
            workspace_root=workspace,
            subpath=".env",
            patch_diff="diff",
            base_checksum=base_checksum,
            dry_run=False,
        )
    assert exc.value.code == ErrorCode.POLICY_DENIED


def test_patch_binary_file_rejected(provider: FilesystemProvider, workspace: Path) -> None:
    bin_file = workspace / "src" / "binary.bin"
    bin_file.write_bytes(b"\x00\x01\x02\x03")
    base_checksum = hashlib.sha256(bin_file.read_bytes()).hexdigest()

    with pytest.raises(TacpValidationError) as exc:
        provider.apply_patch(
            workspace_root=workspace,
            subpath="src/binary.bin",
            patch_diff="diff",
            base_checksum=base_checksum,
            dry_run=False,
        )
    assert "Binary files" in str(exc.value)


def test_patch_size_limit_exceeded(provider: FilesystemProvider, workspace: Path) -> None:
    target = workspace / "src" / "sample.py"
    base_checksum = hashlib.sha256(target.read_bytes()).hexdigest()

    huge_diff = "A" * (provider.limits.max_patch_bytes + 100)
    with pytest.raises(TacpValidationError) as exc:
        provider.apply_patch(
            workspace_root=workspace,
            subpath="src/sample.py",
            patch_diff=huge_diff,
            base_checksum=base_checksum,
            dry_run=False,
        )
    assert "exceeds limit" in str(exc.value)


def test_rollback_patch_success(provider: FilesystemProvider, workspace: Path) -> None:
    target = workspace / "src" / "sample.py"
    orig_text = target.read_text()
    base_checksum = hashlib.sha256(target.read_bytes()).hexdigest()

    diff = (
        "--- a/src/sample.py\n"
        "+++ b/src/sample.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def hello():\n"
        "-    return 42\n"
        "+    return 100\n"
    )

    res = provider.apply_patch(
        workspace_root=workspace,
        subpath="src/sample.py",
        patch_diff=diff,
        base_checksum=base_checksum,
        dry_run=False,
    )
    assert target.read_text() == "def hello():\n    return 100\n"

    # Now rollback
    snapshot_path = Path(res["snapshot_path"])
    rollback_res = provider.rollback_patch(
        workspace_root=workspace,
        subpath="src/sample.py",
        snapshot_path=snapshot_path,
        expected_current_checksum=res["after_checksum"],
    )
    assert rollback_res["status"] == PatchStatus.ROLLED_BACK
    # Target file is restored to original text
    assert target.read_text() == orig_text


def test_rollback_checksum_mismatch_fails(provider: FilesystemProvider, workspace: Path) -> None:
    target = workspace / "src" / "sample.py"
    base_checksum = hashlib.sha256(target.read_bytes()).hexdigest()

    diff = (
        "--- a/src/sample.py\n"
        "+++ b/src/sample.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def hello():\n"
        "-    return 42\n"
        "+    return 100\n"
    )

    res = provider.apply_patch(
        workspace_root=workspace,
        subpath="src/sample.py",
        patch_diff=diff,
        base_checksum=base_checksum,
        dry_run=False,
    )

    # If someone edited the file in between
    target.write_text("def someone_else_edited(): pass\n")

    snapshot_path = Path(res["snapshot_path"])
    with pytest.raises(TacpConflictError):
        provider.rollback_patch(
            workspace_root=workspace,
            subpath="src/sample.py",
            snapshot_path=snapshot_path,
            expected_current_checksum=res["after_checksum"],
        )
