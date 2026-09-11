"""Integration tests for MCP execution.request protocol interactions."""

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import create_mcp_server
from tacp.control.approval import ApprovalEngine
from tacp.infrastructure.config import OutputLimits, TacpConfig
from tacp.infrastructure.database import Database


@pytest.fixture
def mcp_exec_fixture(test_db: Database, tmp_path: Path) -> Dict[str, Any]:
    ws_dir = tmp_path / "mcp_exec_ws"
    ws_dir.mkdir()

    cfg_exec = TacpConfig(
        data_dir=tmp_path / ".tacp_exec",
        db_path=test_db.db_path,
        execution_enabled=True,
        read_only=False,
        limits=OutputLimits(),
    )
    server_exec = create_mcp_server(cfg_exec)
    ws = server_exec.tool_registry.workspace_service.register_workspace("exec_ws", ws_dir)

    cfg_disabled = TacpConfig(
        data_dir=tmp_path / ".tacp_disabled",
        db_path=test_db.db_path,
        execution_enabled=False,
        read_only=True,
        limits=OutputLimits(),
    )
    server_disabled = create_mcp_server(cfg_disabled)

    return {
        "server_exec": server_exec,
        "server_disabled": server_disabled,
        "ws": ws,
        "ws_dir": ws_dir,
        "db": test_db,
    }


def test_tools_list_reflects_execution_flag(mcp_exec_fixture: Dict[str, Any]) -> None:
    server_disabled = mcp_exec_fixture["server_disabled"]
    server_exec = mcp_exec_fixture["server_exec"]

    # When execution is disabled, execution.request is absent
    req_dis = McpRequest(id=1, method="tools/list", params={})
    resp_dis = server_disabled.handle_request(req_dis)
    assert resp_dis is not None
    tool_names_dis = [t["name"] for t in resp_dis.result["tools"]]
    assert "execution.request" not in tool_names_dis

    # When execution is enabled, execution.request is present
    req_en = McpRequest(id=2, method="tools/list", params={})
    resp_en = server_exec.handle_request(req_en)
    assert resp_en is not None
    tool_names_en = [t["name"] for t in resp_en.result["tools"]]
    assert "execution.request" in tool_names_en


def test_mcp_execution_disabled_returns_error(mcp_exec_fixture: Dict[str, Any]) -> None:
    server_disabled = mcp_exec_fixture["server_disabled"]
    ws = mcp_exec_fixture["ws"]

    req = McpRequest(
        id=10,
        method="tools/call",
        params={
            "name": "execution.request",
            "arguments": {
                "workspace_id": ws.id,
                "executable": "printf",
                "argv": ["hello"],
            },
        },
    )
    resp = server_disabled.handle_request(req)
    assert resp is not None
    assert resp.result["isError"] is True
    err_text = resp.result["content"][0]["text"]
    assert "POLICY_DENIED" in err_text or "disabled" in err_text


def test_mcp_execution_dry_run(mcp_exec_fixture: Dict[str, Any]) -> None:
    server_exec = mcp_exec_fixture["server_exec"]
    ws = mcp_exec_fixture["ws"]

    req = McpRequest(
        id=20,
        method="tools/call",
        params={
            "name": "execution.request",
            "arguments": {
                "workspace_id": ws.id,
                "executable": "printf",
                "argv": ["mcp-dry-run-test\\n"],
                "dry_run": True,
            },
        },
    )
    resp = server_exec.handle_request(req)
    assert resp is not None
    assert resp.result["isError"] is False
    content_text = resp.result["content"][0]["text"]
    data = json.loads(content_text)
    assert data["status"] == "DRY_RUN"
    assert data["contract_hash"] != ""
    assert data["exit_code"] is None


def test_mcp_execution_approval_flow_and_live_run(mcp_exec_fixture: Dict[str, Any]) -> None:
    server_exec = mcp_exec_fixture["server_exec"]
    ws = mcp_exec_fixture["ws"]
    db = mcp_exec_fixture["db"]

    # 1. Non-dry-run without approval token -> returns structured APPROVAL_REQUIRED error
    req = McpRequest(
        id=30,
        method="tools/call",
        params={
            "name": "execution.request",
            "arguments": {
                "workspace_id": ws.id,
                "executable": "printf",
                "argv": ["mcp-live-exec-output\\n"],
                "dry_run": False,
            },
        },
    )
    resp = server_exec.handle_request(req)
    assert resp is not None
    assert resp.result["isError"] is True
    err_text = resp.result["content"][0]["text"]
    assert "APPROVAL_REQUIRED" in err_text
    err_obj = json.loads(err_text)
    token = err_obj.get("token") or (err_obj.get("ticket", {}).get("token"))
    assert token is not None
    assert token.startswith("tacp_appr_")

    # 2. Approve ticket via ApprovalEngine
    appr_engine = ApprovalEngine(db)
    appr_engine.approve(token, approved_by="human_operator")

    # 3. Call execution.request with approved token
    req_approved = McpRequest(
        id=31,
        method="tools/call",
        params={
            "name": "execution.request",
            "arguments": {
                "workspace_id": ws.id,
                "executable": "printf",
                "argv": ["mcp-live-exec-output\\n"],
                "dry_run": False,
                "approval_token": token,
            },
        },
    )
    resp_approved = server_exec.handle_request(req_approved)
    assert resp_approved is not None
    assert resp_approved.result["isError"] is False
    content_approved = resp_approved.result["content"][0]["text"]
    res_data = json.loads(content_approved)
    assert res_data["status"] == "SUCCEEDED"
    assert res_data["exit_code"] == 0
    assert "mcp-live-exec-output" in res_data["stdout"]

    # 4. Token replay attempt -> fails because token was single-use consumed
    req_replay = McpRequest(
        id=32,
        method="tools/call",
        params={
            "name": "execution.request",
            "arguments": {
                "workspace_id": ws.id,
                "executable": "printf",
                "argv": ["mcp-live-exec-output\\n"],
                "dry_run": False,
                "approval_token": token,
            },
        },
    )
    resp_replay = server_exec.handle_request(req_replay)
    assert resp_replay is not None
    assert resp_replay.result["isError"] is True


def test_mcp_execution_forbidden_binary_rejected(mcp_exec_fixture: Dict[str, Any]) -> None:
    server_exec = mcp_exec_fixture["server_exec"]
    ws = mcp_exec_fixture["ws"]

    req = McpRequest(
        id=40,
        method="tools/call",
        params={
            "name": "execution.request",
            "arguments": {
                "workspace_id": ws.id,
                "executable": "bash",
                "argv": ["-c", "id"],
                "dry_run": True,
            },
        },
    )
    resp = server_exec.handle_request(req)
    assert resp is not None
    assert resp.result["isError"] is True
    err_text = resp.result["content"][0]["text"]
    assert "forbidden" in err_text.lower()
