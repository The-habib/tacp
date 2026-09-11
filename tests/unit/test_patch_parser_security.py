"""Security and differential validation tests for TACP unified diff parser (Sections 23, 24, 25)."""

import difflib
import hashlib
from pathlib import Path

import pytest

from tacp.domain.errors import ErrorCode, TacpConflictError, TacpValidationError
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
def ws(tmp_path: Path) -> Path:
    root = tmp_path / "test_workspace"
    root.mkdir()
    return root


# ---------------------------------------------------------------------------
# Section 23: Diff Parser Edge Cases & Security
# ---------------------------------------------------------------------------


def test_parser_rejects_empty_or_whitespace_diff(provider: FilesystemProvider, ws: Path) -> None:
    target = ws / "file.txt"
    target.write_text("hello\n")
    csum = hashlib.sha256(b"hello\n").hexdigest()

    with pytest.raises(TacpValidationError) as exc:
        provider.apply_patch(ws, "file.txt", "", csum)
    assert "no unified diff hunks found" in str(exc.value)

    with pytest.raises(TacpValidationError) as exc:
        provider.apply_patch(ws, "file.txt", "   \n\n  ", csum)
    assert "no unified diff hunks found" in str(exc.value)


def test_parser_rejects_missing_hunks(provider: FilesystemProvider, ws: Path) -> None:
    target = ws / "file.txt"
    target.write_text("hello\n")
    csum = hashlib.sha256(b"hello\n").hexdigest()

    diff_only_headers = "--- a/file.txt\n+++ b/file.txt\n"
    with pytest.raises(TacpValidationError) as exc:
        provider.apply_patch(ws, "file.txt", diff_only_headers, csum)
    assert "no unified diff hunks found" in str(exc.value)


def test_parser_rejects_invalid_hunk_header(provider: FilesystemProvider, ws: Path) -> None:
    target = ws / "file.txt"
    target.write_text("hello\n")
    csum = hashlib.sha256(b"hello\n").hexdigest()

    bad_hunk = "--- file.txt\n+++ file.txt\n@@ invalid @@\n-hello\n+world\n"
    with pytest.raises(TacpValidationError) as exc:
        provider.apply_patch(ws, "file.txt", bad_hunk, csum)
    assert "Invalid hunk header" in str(exc.value)


def test_parser_rejects_corrupted_prefix_characters(provider: FilesystemProvider, ws: Path) -> None:
    target = ws / "file.txt"
    target.write_text("line 1\nline 2\n")
    csum = hashlib.sha256(b"line 1\nline 2\n").hexdigest()

    # Prefix '?' is not valid unified diff syntax
    corrupt_diff = "--- file.txt\n+++ file.txt\n@@ -1,2 +1,2 @@\n line 1\n?line 2\n"
    with pytest.raises(TacpValidationError) as exc:
        provider.apply_patch(ws, "file.txt", corrupt_diff, csum)
    assert "Invalid diff line prefix" in str(exc.value)


def test_parser_rejects_hunk_count_mismatch_too_few(provider: FilesystemProvider, ws: Path) -> None:
    target = ws / "file.txt"
    target.write_text("line 1\nline 2\nline 3\n")
    csum = hashlib.sha256(b"line 1\nline 2\nline 3\n").hexdigest()

    # Header specifies 3 lines for old range, but hunk body only has 2 lines
    mismatch_diff = "--- file.txt\n+++ file.txt\n@@ -1,3 +1,3 @@\n line 1\n-line 2\n+new 2\n"
    with pytest.raises(TacpValidationError) as exc:
        provider.apply_patch(ws, "file.txt", mismatch_diff, csum)
    assert "count mismatch" in str(exc.value)


def test_parser_rejects_hunk_count_mismatch_too_many(
    provider: FilesystemProvider, ws: Path
) -> None:
    target = ws / "file.txt"
    target.write_text("line 1\nline 2\n")
    csum = hashlib.sha256(b"line 1\nline 2\n").hexdigest()

    # Header specifies 1 line for old range, but hunk body consumes 2
    mismatch_diff = "--- file.txt\n+++ file.txt\n@@ -1,1 +1,1 @@\n line 1\n line 2\n"
    with pytest.raises(TacpValidationError) as exc:
        provider.apply_patch(ws, "file.txt", mismatch_diff, csum)
    assert "count mismatch" in str(exc.value)


def test_parser_rejects_overlapping_or_out_of_order_hunks(
    provider: FilesystemProvider, ws: Path
) -> None:
    target = ws / "file.txt"
    target.write_text("line 1\nline 2\nline 3\nline 4\nline 5\n")
    csum = hashlib.sha256(target.read_bytes()).hexdigest()

    # Second hunk starts at line 2, which overlaps with first hunk ending at line 3
    overlapping_diff = (
        "--- file.txt\n"
        "+++ file.txt\n"
        "@@ -1,3 +1,3 @@\n"
        " line 1\n"
        "-line 2\n"
        "+LINE 2\n"
        " line 3\n"
        "@@ -2,3 +2,3 @@\n"
        " line 2\n"
        "-line 3\n"
        "+LINE 3\n"
        " line 4\n"
    )
    with pytest.raises(TacpValidationError) as exc:
        provider.apply_patch(ws, "file.txt", overlapping_diff, csum)
    assert "Overlapping or out-of-order hunk" in str(exc.value)


def test_parser_handles_crlf_and_lf(provider: FilesystemProvider, ws: Path) -> None:
    target = ws / "crlf.txt"
    target.write_bytes(b"hello\r\nworld\r\n")
    csum = hashlib.sha256(b"hello\r\nworld\r\n").hexdigest()

    diff = "--- crlf.txt\r\n+++ crlf.txt\r\n@@ -1,2 +1,2 @@\r\n hello\r\n-world\r\n+Termux\r\n"
    res = provider.apply_patch(ws, "crlf.txt", diff, csum)
    assert res["status"] == PatchStatus.APPLIED
    assert target.read_text().splitlines() == ["hello", "Termux"]


def test_parser_handles_multibyte_unicode_and_emojis(
    provider: FilesystemProvider, ws: Path
) -> None:
    target = ws / "unicode.txt"
    target.write_text("こんにちは世界\n🚀 Termux Control Plane\nÜberprüfung erforderlich\n")
    csum = hashlib.sha256(target.read_bytes()).hexdigest()

    diff = (
        "--- unicode.txt\n"
        "+++ unicode.txt\n"
        "@@ -1,3 +1,3 @@\n"
        " こんにちは世界\n"
        "-🚀 Termux Control Plane\n"
        "+✨ Termux AI Control Plane 🛡️\n"
        " Überprüfung erforderlich\n"
    )
    res = provider.apply_patch(ws, "unicode.txt", diff, csum)
    assert res["status"] == PatchStatus.APPLIED
    content = target.read_text()
    assert "✨ Termux AI Control Plane 🛡️" in content
    assert "Überprüfung erforderlich" in content


def test_parser_handles_file_truncation_to_empty(provider: FilesystemProvider, ws: Path) -> None:
    target = ws / "empty_out.txt"
    target.write_text("first line\nsecond line\n")
    csum = hashlib.sha256(target.read_bytes()).hexdigest()

    diff = "--- empty_out.txt\n+++ empty_out.txt\n@@ -1,2 +0,0 @@\n-first line\n-second line\n"
    res = provider.apply_patch(ws, "empty_out.txt", diff, csum)
    assert res["status"] == PatchStatus.APPLIED
    assert target.read_text() == ""


# ---------------------------------------------------------------------------
# Section 24: Differential Testing with Python difflib
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "orig_lines, new_lines",
    [
        (
            ["alpha\n", "beta\n", "gamma\n", "delta\n"],
            ["alpha\n", "BETA-MODIFIED\n", "gamma\n", "delta\n", "epsilon\n"],
        ),
        (
            ["header\n", "item 1\n", "item 2\n", "footer\n"],
            ["header\n", "new item A\n", "item 2\n", "footer\n"],
        ),
        (
            ["line A\n", "line B\n", "line C\n", "line D\n", "line E\n"],
            ["line A\n", "line B\n", "line D\n"],
        ),
        (
            ["start\n", "mid 1\n", "mid 2\n", "mid 3\n", "end\n"],
            ["start\n", "REPLACED MID\n", "end\n"],
        ),
    ],
)
def test_differential_difflib_validation(
    provider: FilesystemProvider,
    ws: Path,
    orig_lines: list[str],
    new_lines: list[str],
) -> None:
    """Validate that diffs produced by standard difflib apply with 100% fidelity."""
    file_path = ws / "diff_test.txt"
    orig_content = "".join(orig_lines)
    expected_content = "".join(new_lines)

    file_path.write_text(orig_content)
    base_checksum = hashlib.sha256(orig_content.encode("utf-8")).hexdigest()

    diff_gen = difflib.unified_diff(
        orig_lines,
        new_lines,
        fromfile="diff_test.txt",
        tofile="diff_test.txt",
    )
    diff_text = "".join(diff_gen)
    assert diff_text != "", "difflib must produce a non-empty diff"

    res = provider.apply_patch(
        workspace_root=ws,
        subpath="diff_test.txt",
        patch_diff=diff_text,
        base_checksum=base_checksum,
        dry_run=False,
    )
    assert res["status"] == PatchStatus.APPLIED
    assert file_path.read_text() == expected_content


# ---------------------------------------------------------------------------
# Section 25: Idempotency & Replay Defense
# ---------------------------------------------------------------------------


def test_patch_replay_defense_fails_with_conflict(provider: FilesystemProvider, ws: Path) -> None:
    """Applying a patch once succeeds; replaying the same patch must raise TacpConflictError."""
    target = ws / "replay.txt"
    target.write_text("original content\n")
    orig_checksum = hashlib.sha256(b"original content\n").hexdigest()

    diff = "--- replay.txt\n+++ replay.txt\n@@ -1 +1 @@\n-original content\n+updated content\n"

    # First execution succeeds
    res = provider.apply_patch(ws, "replay.txt", diff, orig_checksum)
    assert res["status"] == PatchStatus.APPLIED
    assert target.read_text() == "updated content\n"

    # Second execution with original base_checksum fails with TacpConflictError
    with pytest.raises(TacpConflictError) as exc:
        provider.apply_patch(ws, "replay.txt", diff, orig_checksum)
    assert exc.value.code == ErrorCode.CONFLICT
