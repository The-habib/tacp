"""Integration tests for TACP CLI execution commands."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tacp.cli.main import main


def test_cli_execution_list_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tacp_dir = tmp_path / "tacp_data"
    with patch.dict(os.environ, {"TACP_DATA_DIR": str(tacp_dir)}):
        main(["doctor"])
        capsys.readouterr()

        code = main(["execution", "list"])
        assert code == 0
        captured = capsys.readouterr()
        assert "No execution records found." in captured.out


def test_cli_execution_request_disabled_by_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tacp_dir = tmp_path / "tacp_data"
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()

    with patch.dict(os.environ, {"TACP_DATA_DIR": str(tacp_dir)}):
        main(["doctor"])
        main(["workspace", "add", str(ws_dir), "--name", "test-ws"])
        capsys.readouterr()

        # Without --allow-execution
        code = main(
            [
                "execution",
                "request",
                "--workspace",
                "test-ws",
                "--executable",
                "echo",
                "--args",
                "hello",
            ]
        )
        assert code != 0
        captured = capsys.readouterr()
        assert "Execution Error" in captured.out or "Execution is disabled" in captured.out


def test_cli_execution_request_dry_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tacp_dir = tmp_path / "tacp_data"
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()

    with patch.dict(os.environ, {"TACP_DATA_DIR": str(tacp_dir)}):
        main(["doctor"])
        main(["workspace", "add", str(ws_dir), "--name", "test-ws"])
        capsys.readouterr()

        code = main(
            [
                "execution",
                "request",
                "--workspace",
                "test-ws",
                "--executable",
                "echo",
                "--args",
                "dry",
                "run",
                "test",
                "--dry-run",
                "--allow-execution",
            ]
        )
        assert code == 0
        captured = capsys.readouterr()
        assert "DRY_RUN" in captured.out


def test_cli_execution_request_live_and_inspect(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tacp_dir = tmp_path / "tacp_data"
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()

    with patch.dict(os.environ, {"TACP_DATA_DIR": str(tacp_dir)}):
        main(["doctor"])
        main(["workspace", "add", str(ws_dir), "--name", "test-ws"])
        capsys.readouterr()

        # First: Without --auto-approve, execution requires approval
        code_no_appr = main(
            [
                "execution",
                "request",
                "--workspace",
                "test-ws",
                "--executable",
                "printf",
                "--args",
                "cli-test-output\\n",
                "--allow-execution",
            ]
        )
        assert code_no_appr != 0
        cap_no_appr = capsys.readouterr()
        assert "requires explicit human approval" in cap_no_appr.out

        # Run with --auto-approve and --json
        code = main(
            [
                "execution",
                "request",
                "--workspace",
                "test-ws",
                "--executable",
                "printf",
                "--args",
                "cli-test-output\\n",
                "--allow-execution",
                "--auto-approve",
                "--json",
            ]
        )
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "SUCCEEDED"
        assert data["exit_code"] == 0
        assert "cli-test-output" in data["stdout"]
        exec_id = data["execution_id"]

        # Inspect execution
        code_inspect = main(["execution", "inspect", exec_id])
        assert code_inspect == 0
        cap_inspect = capsys.readouterr()
        inspect_data = json.loads(cap_inspect.out)
        assert inspect_data["execution_id"] == exec_id
        assert inspect_data["status"] == "SUCCEEDED"

        # List executions
        code_list = main(["execution", "list"])
        assert code_list == 0
        cap_list = capsys.readouterr()
        assert exec_id in cap_list.out
        assert "SUCCEEDED" in cap_list.out


def test_cli_execution_emergency_stop(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tacp_dir = tmp_path / "tacp_data"
    with patch.dict(os.environ, {"TACP_DATA_DIR": str(tacp_dir)}):
        main(["doctor"])
        capsys.readouterr()

        code = main(["execution", "emergency-stop"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Emergency stop completed" in captured.out
