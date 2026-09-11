"""Tests for TACP Configuration (Category A & B)."""

import os
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import pytest

from tacp.infrastructure.config import OutputLimits, TacpConfig


def test_default_config_creation() -> None:
    config = TacpConfig()
    assert config.read_only is True
    assert config.log_level == "INFO"
    assert isinstance(config.data_dir, Path)
    assert isinstance(config.db_path, Path)
    assert config.version == "0.1.0"


def test_config_immutability_frozen() -> None:
    config = TacpConfig()
    with pytest.raises(FrozenInstanceError):
        config.read_only = False  # type: ignore[misc]


def test_output_limits_defaults() -> None:
    limits = OutputLimits()
    assert limits.max_file_read_bytes == 65536
    assert limits.max_dir_entries == 200
    assert limits.max_search_results == 100
    assert limits.max_processes == 100
    assert limits.max_audit_results == 100


def test_output_limits_immutability() -> None:
    limits = OutputLimits()
    with pytest.raises(FrozenInstanceError):
        limits.max_file_read_bytes = 1000  # type: ignore[misc]


def test_config_env_override_data_dir(tmp_path: Path) -> None:
    custom_dir = tmp_path / "custom_data"
    with patch.dict(os.environ, {"TACP_DATA_DIR": str(custom_dir)}):
        config = TacpConfig.load()
        assert config.data_dir == custom_dir.resolve()
        assert config.db_path == (custom_dir / "tacp.db").resolve()


def test_config_env_override_db_path(tmp_path: Path) -> None:
    custom_db = tmp_path / "custom.db"
    with patch.dict(os.environ, {"TACP_DB_PATH": str(custom_db)}):
        config = TacpConfig.load()
        assert config.db_path == custom_db.resolve()


def test_config_env_override_log_level() -> None:
    with patch.dict(os.environ, {"TACP_LOG_LEVEL": "debug"}):
        config = TacpConfig.load()
        assert config.log_level == "DEBUG"


def test_config_database_path_property(tmp_path: Path) -> None:
    config = TacpConfig(data_dir=tmp_path, db_path=tmp_path / "db.sqlite")
    assert config.database_path == tmp_path / "db.sqlite"


def test_config_default_workspace_roots() -> None:
    config = TacpConfig()
    assert len(config.allowed_workspace_roots) >= 1
    assert config.allowed_workspace_roots[0] == Path.home() / "projects"


def test_custom_output_limits_assignment(tmp_path: Path) -> None:
    custom_limits = OutputLimits(max_file_read_bytes=1024, max_dir_entries=50)
    config = TacpConfig(data_dir=tmp_path, limits=custom_limits)
    assert config.limits.max_file_read_bytes == 1024
    assert config.limits.max_dir_entries == 50
