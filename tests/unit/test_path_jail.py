"""Tests for Filesystem Path Jail and Symlink Containment (Category C)."""

from pathlib import Path

import pytest

from tacp.domain.errors import ErrorCode, TacpNotFoundError, TacpSecurityError
from tacp.providers.filesystem import FilesystemProvider


@pytest.fixture
def jail_root(tmp_path: Path) -> Path:
    root = tmp_path / "jail_root"
    root.mkdir()
    (root / "safe_file.txt").write_text("safe content")
    sub = root / "subdir"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested content")
    return root


def test_resolve_safe_subpath(jail_root: Path) -> None:
    provider = FilesystemProvider()
    resolved = provider._resolve_in_jail(jail_root, "safe_file.txt")
    assert resolved == (jail_root / "safe_file.txt").resolve()


def test_resolve_empty_subpath_resolves_to_root(jail_root: Path) -> None:
    provider = FilesystemProvider()
    resolved = provider._resolve_in_jail(jail_root, "")
    assert resolved == jail_root.resolve()


def test_resolve_nested_subpath(jail_root: Path) -> None:
    provider = FilesystemProvider()
    resolved = provider._resolve_in_jail(jail_root, "subdir/nested.txt")
    assert resolved == (jail_root / "subdir" / "nested.txt").resolve()


def test_block_simple_parent_traversal(jail_root: Path) -> None:
    provider = FilesystemProvider()
    with pytest.raises(TacpSecurityError) as exc_info:
        provider._resolve_in_jail(jail_root, "../outside.txt")
    assert exc_info.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_block_deep_traversal_attack(jail_root: Path) -> None:
    provider = FilesystemProvider()
    with pytest.raises(TacpSecurityError) as exc_info:
        provider._resolve_in_jail(jail_root, "../../../../../../../../etc/passwd")
    assert exc_info.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_block_absolute_path_escape(jail_root: Path) -> None:
    provider = FilesystemProvider()
    with pytest.raises(TacpSecurityError) as exc_info:
        provider._resolve_in_jail(jail_root, "/etc/passwd")
    assert exc_info.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_block_null_byte_injection(jail_root: Path) -> None:
    provider = FilesystemProvider()
    with pytest.raises((TacpSecurityError, ValueError)):
        provider._resolve_in_jail(jail_root, "safe_file.txt\x00/../../etc/passwd")


def test_block_symlink_pointing_outside_root(jail_root: Path, tmp_path: Path) -> None:
    outside_target = tmp_path / "secret_outside.txt"
    outside_target.write_text("classified data outside jail")

    outside_symlink = jail_root / "evil_symlink.txt"
    outside_symlink.symlink_to(outside_target)

    provider = FilesystemProvider()
    with pytest.raises(TacpSecurityError) as exc_info:
        provider.read_file(jail_root, "evil_symlink.txt")
    assert exc_info.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_allow_symlink_pointing_inside_root(jail_root: Path) -> None:
    inside_target = jail_root / "safe_file.txt"
    inside_symlink = jail_root / "good_symlink.txt"
    inside_symlink.symlink_to(inside_target)

    provider = FilesystemProvider()
    result = provider.read_file(jail_root, "good_symlink.txt")
    assert result["content"] == "safe content"


def test_block_symlink_directory_escape(jail_root: Path, tmp_path: Path) -> None:
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("confidential")

    symlink_dir = jail_root / "linked_dir"
    symlink_dir.symlink_to(outside_dir)

    provider = FilesystemProvider()
    with pytest.raises(TacpSecurityError) as exc_info:
        provider.list_dir(jail_root, "linked_dir")
    assert exc_info.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_nonexistent_file_inside_jail_raises_not_found(jail_root: Path) -> None:
    provider = FilesystemProvider()
    with pytest.raises(TacpNotFoundError) as exc_info:
        provider.read_file(jail_root, "subdir/does_not_exist.txt")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_traversal_in_middle_of_path(jail_root: Path) -> None:
    provider = FilesystemProvider()
    with pytest.raises(TacpSecurityError) as exc_info:
        provider._resolve_in_jail(jail_root, "subdir/../../../../etc/hosts")
    assert exc_info.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_stat_outside_jail_blocked(jail_root: Path) -> None:
    provider = FilesystemProvider()
    with pytest.raises(TacpSecurityError) as exc_info:
        provider.stat_path(jail_root, "../outside")
    assert exc_info.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_search_outside_jail_blocked(jail_root: Path) -> None:
    provider = FilesystemProvider()
    with pytest.raises(TacpSecurityError) as exc_info:
        provider.search_files(jail_root, query="test", subpath="../outside")
    assert exc_info.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_redundant_slashes_do_not_escape(jail_root: Path) -> None:
    provider = FilesystemProvider()
    resolved = provider._resolve_in_jail(jail_root, "subdir///nested.txt")
    assert resolved == (jail_root / "subdir" / "nested.txt").resolve()
