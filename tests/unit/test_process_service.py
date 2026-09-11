"""Tests for Process Provider and Service (Category D)."""

import os
from unittest.mock import MagicMock, patch

import pytest

from tacp.core.process_service import ProcessService
from tacp.domain.errors import ErrorCode, TacpNotFoundError, TacpSecurityError, TacpValidationError
from tacp.infrastructure.config import OutputLimits
from tacp.providers.process import ProcessProvider


def test_list_processes_structure() -> None:
    provider = ProcessProvider()
    res = provider.list_processes()
    assert "processes" in res
    assert "total_count" in res
    assert "truncated" in res
    assert isinstance(res["processes"], list)


def test_list_processes_contains_current_pid() -> None:
    current_pid = os.getpid()
    provider = ProcessProvider()
    res = provider.list_processes()
    pids = [p["pid"] for p in res["processes"]]
    assert current_pid in pids


def test_inspect_process_current_pid() -> None:
    current_pid = os.getpid()
    provider = ProcessProvider()
    proc_info = provider.inspect_process(current_pid)
    assert proc_info["pid"] == current_pid
    assert "name" in proc_info
    assert "uid" in proc_info
    assert proc_info["uid"] == os.getuid()


def test_inspect_process_nonexistent_pid() -> None:
    provider = ProcessProvider()
    with pytest.raises(TacpNotFoundError) as exc_info:
        provider.inspect_process(999999999)
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_inspect_process_negative_pid_rejected() -> None:
    provider = ProcessProvider()
    with pytest.raises(TacpValidationError) as exc_info:
        provider.inspect_process(-1)
    assert exc_info.value.code == ErrorCode.INVALID_INPUT


def test_inspect_process_zero_pid_rejected() -> None:
    provider = ProcessProvider()
    with pytest.raises(TacpValidationError) as exc_info:
        provider.inspect_process(0)
    assert exc_info.value.code == ErrorCode.INVALID_INPUT


def test_inspect_process_foreign_uid_blocked() -> None:
    provider = ProcessProvider()
    # Mock stat returning a different UID (e.g. root UID 0)
    mock_stat = MagicMock()
    mock_stat.st_uid = 0

    with patch("pathlib.Path.stat", return_value=mock_stat):
        with patch("pathlib.Path.exists", return_value=True):
            with pytest.raises(TacpSecurityError) as exc_info:
                provider.inspect_process(1)
            assert exc_info.value.code == ErrorCode.NOT_AUTHORIZED


def test_process_list_truncation() -> None:
    limits = OutputLimits(max_processes=1)
    provider = ProcessProvider(limits=limits)
    res = provider.list_processes()
    assert len(res["processes"]) <= 1


def test_process_service_delegates_to_provider() -> None:
    provider = ProcessProvider()
    service = ProcessService(provider)
    res = service.list_processes()
    assert "processes" in res
    assert isinstance(res["processes"], list)


def test_process_service_inspect_delegation() -> None:
    provider = ProcessProvider()
    service = ProcessService(provider)
    proc_info = service.inspect_process(os.getpid())
    assert proc_info["pid"] == os.getpid()
