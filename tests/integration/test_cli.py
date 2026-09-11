"""Tests for TACP CLI Commands (Category K)."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tacp import __version__
from tacp.cli.main import main


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["version"])
    assert code == 0
    captured = capsys.readouterr()
    assert f"TACP v{__version__}" in captured.out
    assert "MCP 2026-07-28" in captured.out


def test_cli_capabilities(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["capabilities"])
    assert code == 0
    captured = capsys.readouterr()
    assert "system.inspect" in captured.out
    assert "fs.read" in captured.out
    assert "Total capabilities: 13" in captured.out


def test_cli_doctor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tacp_dir = tmp_path / "cli_doctor_tacp"
    with patch.dict(os.environ, {"TACP_DATA_DIR": str(tacp_dir)}):
        code = main(["doctor"])
        assert code == 0
        captured = capsys.readouterr()
        assert "[PASS] Python Runtime:" in captured.out
        assert "[PASS] SQLite Database:" in captured.out
        assert "[OK] All critical doctor checks passed." in captured.out


def test_cli_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tacp_dir = tmp_path / "cli_status_tacp"
    with patch.dict(os.environ, {"TACP_DATA_DIR": str(tacp_dir)}):
        code = main(["status"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Overall Health" in captured.out
        assert "Database Healthy : True" in captured.out


def test_cli_workspace_workflow(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tacp_dir = tmp_path / "cli_ws_tacp"
    ws_dir = tmp_path / "target_workspace"
    ws_dir.mkdir()

    with patch.dict(os.environ, {"TACP_DATA_DIR": str(tacp_dir)}):
        # 1. Add workspace
        code_add = main(["workspace", "add", str(ws_dir), "--name", "my-test-ws"])
        assert code_add == 0
        cap_add = capsys.readouterr()
        assert "Registered workspace 'my-test-ws'" in cap_add.out

        # 2. List workspaces
        code_list = main(["workspace", "list"])
        assert code_list == 0
        cap_list = capsys.readouterr()
        assert "my-test-ws" in cap_list.out


def test_cli_audit_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tacp_dir = tmp_path / "cli_audit_tacp"
    with patch.dict(os.environ, {"TACP_DATA_DIR": str(tacp_dir)}):
        # Initialize db with doctor first
        main(["doctor"])
        capsys.readouterr()

        code = main(["audit"])
        assert code == 0


def test_cli_audit_json_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tacp_dir = tmp_path / "cli_audit_json_tacp"
    with patch.dict(os.environ, {"TACP_DATA_DIR": str(tacp_dir)}):
        main(["doctor"])
        capsys.readouterr()

        code = main(["audit", "--json"])
        assert code == 0
        captured = capsys.readouterr()
        assert "[]" in captured.out or "[" in captured.out


def test_cli_no_args_shows_help(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([])
    assert code == 0
    captured = capsys.readouterr()
    assert "usage: tacp" in captured.out
