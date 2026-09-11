"""Tests for Filesystem Output Limits and Content Truncation (Category C)."""

from pathlib import Path

import pytest

from tacp.domain.errors import ErrorCode, TacpSecurityError
from tacp.infrastructure.config import OutputLimits
from tacp.providers.filesystem import FilesystemProvider


@pytest.fixture
def limits_root(tmp_path: Path) -> Path:
    root = tmp_path / "limits_root"
    root.mkdir()
    return root


def test_read_file_within_limit(limits_root: Path) -> None:
    f = limits_root / "short.txt"
    f.write_text("A" * 100)

    limits = OutputLimits(max_file_read_bytes=500)
    provider = FilesystemProvider(limits=limits)
    res = provider.read_file(limits_root, "short.txt")

    assert res["bytes_read"] == 100
    assert res["truncated"] is False
    assert res["content"] == "A" * 100


def test_read_file_truncation_at_limit(limits_root: Path) -> None:
    f = limits_root / "large.txt"
    f.write_text("B" * 2000)

    limits = OutputLimits(max_file_read_bytes=500)
    provider = FilesystemProvider(limits=limits)
    res = provider.read_file(limits_root, "large.txt")

    assert res["bytes_read"] == 500
    assert res["truncated"] is True
    assert len(res["content"]) == 500
    assert res["total_size_bytes"] == 2000


def test_list_dir_entry_cap(limits_root: Path) -> None:
    for i in range(25):
        (limits_root / f"file_{i:02d}.txt").write_text("data")

    limits = OutputLimits(max_dir_entries=10)
    provider = FilesystemProvider(limits=limits)
    res = provider.list_dir(limits_root, "")

    assert len(res["entries"]) == 10
    assert res["truncated"] is True
    assert res["total_count"] == 25


def test_search_results_cap(limits_root: Path) -> None:
    for i in range(15):
        (limits_root / f"search_target_{i:02d}.txt").write_text("TARGET_PATTERN_FOUND")

    limits = OutputLimits(max_search_results=5)
    provider = FilesystemProvider(limits=limits)
    res = provider.search_files(limits_root, query="TARGET_PATTERN_FOUND")

    assert len(res["matches"]) == 5
    assert res["truncated"] is True


def test_binary_file_detection_and_blocking(limits_root: Path) -> None:
    bin_file = limits_root / "binary.bin"
    bin_file.write_bytes(b"\x00\x01\x02\x03\x04\xff\xfe\xfd")

    provider = FilesystemProvider()
    with pytest.raises(TacpSecurityError) as exc_info:
        provider.read_file(limits_root, "binary.bin")
    assert exc_info.value.code == ErrorCode.RESOURCE_LIMIT


def test_empty_file_read(limits_root: Path) -> None:
    empty_f = limits_root / "empty.txt"
    empty_f.write_text("")

    provider = FilesystemProvider()
    res = provider.read_file(limits_root, "empty.txt")
    assert res["bytes_read"] == 0
    assert res["truncated"] is False
    assert res["content"] == ""


def test_search_case_sensitivity(limits_root: Path) -> None:
    f = limits_root / "test_case.txt"
    f.write_text("Search Target In Here")

    provider = FilesystemProvider()
    res_lower = provider.search_files(limits_root, query="target", case_sensitive=False)
    assert len(res_lower["matches"]) == 1

    res_upper = provider.search_files(limits_root, query="target", case_sensitive=True)
    assert len(res_upper["matches"]) == 0


def test_list_dir_returns_classification(limits_root: Path) -> None:
    (limits_root / "public.txt").write_text("public")
    (limits_root / "id_rsa").write_text("key")

    provider = FilesystemProvider()
    res = provider.list_dir(limits_root, "")

    classifications = {e["name"]: e["classification"] for e in res["entries"]}
    assert classifications["public.txt"] == "PUBLIC"
    assert classifications["id_rsa"] == "SECRET"


def test_stat_path_includes_classification(limits_root: Path) -> None:
    f = limits_root / ".env"
    f.write_text("SECRET=123")

    provider = FilesystemProvider()
    st = provider.stat_path(limits_root, ".env")
    assert st["classification"] == "SECRET"
    assert st["is_file"] is True


def test_stat_directory(limits_root: Path) -> None:
    d = limits_root / "testdir"
    d.mkdir()

    provider = FilesystemProvider()
    st = provider.stat_path(limits_root, "testdir")
    assert st["is_dir"] is True
    assert st["is_file"] is False
