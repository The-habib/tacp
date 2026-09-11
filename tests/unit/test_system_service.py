"""Tests for System Provider and Service (Category E)."""

from unittest.mock import MagicMock

from tacp import __version__
from tacp.core.system_service import SystemService
from tacp.infrastructure.database import Database
from tacp.providers.system import SystemProvider


def test_system_info_structure() -> None:
    provider = SystemProvider()
    info = provider.get_system_info()
    assert "os" in info
    assert "arch" in info
    assert "python_version" in info
    assert "termux" in info
    assert "memory" in info
    assert "storage" in info


def test_system_provider_storage_info() -> None:
    provider = SystemProvider()
    storage = provider._get_storage()
    assert "free_mb" in storage
    assert "total_mb" in storage
    assert storage["total_mb"] > 0


def test_system_provider_memory_info() -> None:
    provider = SystemProvider()
    mem = provider._get_memory()
    assert isinstance(mem, dict)


def test_system_provider_health_status() -> None:
    provider = SystemProvider()
    health = provider.get_health()
    assert "status" in health
    assert health["status"] in ("HEALTHY", "WARNING", "CRITICAL")
    assert "checks" in health


def test_system_service_inspect_system(test_db: Database) -> None:
    service = SystemService(test_db)
    info = service.inspect_system()
    assert "python_version" in info


def test_system_service_get_health(test_db: Database) -> None:
    service = SystemService(test_db)
    health = service.get_health()
    assert health["status"] in ("HEALTHY", "DEGRADED")
    assert health["database_healthy"] is True
    assert "system_health" in health


def test_system_service_get_version() -> None:
    ver = SystemService.get_version()
    assert ver["tacp_version"] == __version__
    assert ver["mcp_protocol_version"] == "2026-07-28"
    assert ver["mode"] in ("READ_ONLY", "GOVERNED")


def test_system_service_degraded_when_db_unhealthy() -> None:
    mock_db = MagicMock()
    mock_db.is_healthy.return_value = False

    service = SystemService(mock_db)
    health = service.get_health()
    assert health["status"] == "DEGRADED"
    assert health["database_healthy"] is False


def test_termux_detection_in_system_info() -> None:
    provider = SystemProvider()
    info = provider.get_system_info()
    assert isinstance(info["termux"], dict)
    assert "is_termux" in info["termux"]


def test_system_health_storage_margin_check() -> None:
    provider = SystemProvider()
    health = provider.get_health()
    checks = health.get("checks", {})
    assert "storage_margin" in checks
