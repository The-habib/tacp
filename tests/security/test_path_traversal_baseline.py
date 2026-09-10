"""Security tests for path canonicalization and sandbox boundaries."""

from pathlib import Path


def is_path_safe(base_dir: Path, requested_path: str) -> bool:
    """Basic path traversal check demonstrating the canonicalization invariant."""
    resolved_base = base_dir.resolve()
    target = (resolved_base / requested_path).resolve()
    try:
        target.relative_to(resolved_base)
        return True
    except ValueError:
        return False


def test_path_traversal_rejection(tmp_path: Path) -> None:
    """Verify that path traversal attempts are detected and rejected."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert is_path_safe(workspace, "valid_file.txt") is True
    assert is_path_safe(workspace, "sub/dir/nested.txt") is True
    assert is_path_safe(workspace, "../escape.txt") is False
    assert is_path_safe(workspace, "../../../../etc/passwd") is False
