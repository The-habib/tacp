"""On-device environment verification tests for Termux/Android/Linux."""

import os
import platform
import sys
from pathlib import Path

import pytest

from tacp.providers.process import ProcessProvider
from tacp.providers.system import SystemProvider

pytestmark = pytest.mark.device


def test_device_is_linux_or_android() -> None:
    system_name = platform.system().lower()
    assert system_name in ("linux", "android")


def test_device_python_version_ge_311() -> None:
    assert sys.version_info >= (3, 11)


def test_device_proc_filesystem_accessible() -> None:
    proc = Path("/proc")
    assert proc.exists()
    assert proc.is_dir()


def test_device_current_user_has_valid_uid() -> None:
    uid = os.getuid()
    assert isinstance(uid, int)
    assert uid >= 0


def test_device_system_provider_live_execution() -> None:
    provider = SystemProvider()
    info = provider.get_system_info()
    assert info["arch"] in ["aarch64", "x86_64", "armv7l", "arm64", "i686", "arm"]
    assert "kernel" in info


def test_device_process_provider_live_execution() -> None:
    provider = ProcessProvider()
    res = provider.list_processes()
    assert res["total_count"] >= 1
    # Current process must be in the list
    pids = [p["pid"] for p in res["processes"]]
    assert os.getpid() in pids


def test_device_storage_free_space_positive() -> None:
    provider = SystemProvider()
    storage = provider._get_storage()
    assert storage["free_mb"] > 0
    assert storage["total_mb"] > 0
