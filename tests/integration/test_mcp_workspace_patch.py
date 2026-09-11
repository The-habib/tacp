"""Integration tests for MCP workspace.patch protocol interactions (Category K & M)."""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import create_mcp_server
from tacp.control.approval import ApprovalEngine
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database


@pytest.fixture
def mcp_fixture(test_db: Database, tmp_path: Path) -> Dict[str, Any]:
    ws_dir = tmp_path / "mcp_project"
    ws_dir.mkdir()
    (ws_dir / "src").mkdir()
    sample_file = ws_dir / "src" / "code.py"
    sample_file.write_text("a = 1\nb = 2\n")

    cfg_mut = TacpConfig(
        data_dir=tmp_path / ".tacp_mut",
        db_path=test_db.db_path,
        mutation_enabled=True,
        read_only=False,
    )
    server_mut = create_mcp_server(cfg_mut)

    # Register workspace
    ws = server_mut.tool_registry.workspace_service.register_workspace("mcp_ws", ws_dir)

    cfg_ro = TacpConfig(
        data_dir=tmp_path / ".tacp_ro",
        db_path=test_db.db_path,
        mutation_enabled=False,
        read_only=True,
    )
    server_ro = create_mcp_server(cfg_ro)

    return {
        "server_mut": server_mut,
        "server_ro": server_ro,
        "ws": ws,
        "sample_file": sample_file,
        "db": test_db,
    }


def test_tools_list_reflects_mutation_flag(mcp_fixture: Dict[str, Any]) -> None:
    server_ro = mcp_fixture["server_ro"]
    server_mut = mcp_fixture["server_mut"]

    # When mutation disabled: exactly 13 tools, no workspace.patch
    req_ro = McpRequest(id=1, method="tools/list", params={})
    resp_ro = server_ro.handle_request(req_ro)
    assert resp_ro is not None
    tool_names_ro = [t["name"] for t in resp_ro.result["tools"]]
    assert len(tool_names_ro) == 13
    assert "workspace.patch" not in tool_names_ro

    # When mutation enabled: exactly 14 tools, includes workspace.patch
    req_mut = McpRequest(id=2, method="tools/list", params={})
    resp_mut = server_mut.handle_request(req_mut)
    assert resp_mut is not None
    tool_names_mut = [t["name"] for t in resp_mut.result["tools"]]
    assert len(tool_names_mut) == 14
    assert "workspace.patch" in tool_names_mut


def test_mcp_tool_call_dry_run(mcp_fixture: Dict[str, Any]) -> None:
    server_mut = mcp_fixture["server_mut"]
    ws = mcp_fixture["ws"]
    sample_file = mcp_fixture["sample_file"]
    base_hash = hashlib.sha256(sample_file.read_bytes()).hexdigest()

    diff = "--- a/src/code.py\n+++ b/src/code.py\n@@ -1,2 +1,2 @@\n-a = 1\n+a = 10\n b = 2\n"

    req = McpRequest(
        id=10,
        method="tools/call",
        params={
            "name": "tacp_workspace_patch",
            "arguments": {
                "workspace_id": ws.id,
                "subpath": "src/code.py",
                "patch_content": diff,
                "base_checksum": base_hash,
                "dry_run": True,
            },
        },
    )
    resp = server_mut.handle_request(req)
    assert resp is not None
    assert resp.result["isError"] is False
    content_text = resp.result["content"][0]["text"]
    parsed = json.loads(content_text)
    assert parsed["status"] == "SIMULATED"
    assert parsed["lines_added"] == 1
    assert parsed["lines_removed"] == 1
    # File not changed
    assert sample_file.read_text() == "a = 1\nb = 2\n"


def test_mcp_tool_call_without_approval_returns_error(mcp_fixture: Dict[str, Any]) -> None:
    server_mut = mcp_fixture["server_mut"]
    ws = mcp_fixture["ws"]
    sample_file = mcp_fixture["sample_file"]
    base_hash = hashlib.sha256(sample_file.read_bytes()).hexdigest()

    diff = "--- a/src/code.py\n+++ b/src/code.py\n@@ -1,2 +1,2 @@\n-a = 1\n+a = 10\n b = 2\n"

    req = McpRequest(
        id=11,
        method="tools/call",
        params={
            "name": "workspace.patch",
            "arguments": {
                "workspace_id": ws.id,
                "subpath": "src/code.py",
                "patch_content": diff,
                "base_checksum": base_hash,
                "dry_run": False,
            },
        },
    )
    resp = server_mut.handle_request(req)
    assert resp is not None
    assert resp.result["isError"] is True
    error_text = resp.result["content"][0]["text"]
    assert "APPROVAL_REQUIRED" in error_text
    assert "Ticket created" in error_text


def test_mcp_tool_call_with_approval_succeeds(mcp_fixture: Dict[str, Any]) -> None:
    server_mut = mcp_fixture["server_mut"]
    ws = mcp_fixture["ws"]
    sample_file = mcp_fixture["sample_file"]
    base_hash = hashlib.sha256(sample_file.read_bytes()).hexdigest()

    diff = "--- a/src/code.py\n+++ b/src/code.py\n@@ -1,2 +1,2 @@\n-a = 1\n+a = 10\n b = 2\n"
    diff_hash = hashlib.sha256(diff.encode("utf-8")).hexdigest()

    # Pre-approve ticket
    appr_engine = ApprovalEngine(mcp_fixture["db"])
    ticket = appr_engine.create_ticket(
        principal_id="mcp-client",
        action_type="workspace.patch",
        workspace_id=ws.id,
        target_path="src/code.py",
        patch_hash=diff_hash,
    )
    appr_engine.approve(ticket.token)

    req = McpRequest(
        id=12,
        method="tools/call",
        params={
            "name": "workspace.patch",
            "arguments": {
                "workspace_id": ws.id,
                "subpath": "src/code.py",
                "patch_content": diff,
                "base_checksum": base_hash,
                "dry_run": False,
                "approval_token": ticket.token,
            },
        },
    )
    resp = server_mut.handle_request(req)
    assert resp is not None
    assert resp.result["isError"] is False
    content_text = resp.result["content"][0]["text"]
    parsed = json.loads(content_text)
    assert parsed["status"] == "APPLIED"
    assert sample_file.read_text() == "a = 10\nb = 2\n"


def test_mcp_tool_call_when_mutation_disabled_fails(mcp_fixture: Dict[str, Any]) -> None:
    server_ro = mcp_fixture["server_ro"]
    ws = mcp_fixture["ws"]
    sample_file = mcp_fixture["sample_file"]
    base_hash = hashlib.sha256(sample_file.read_bytes()).hexdigest()

    req = McpRequest(
        id=13,
        method="tools/call",
        params={
            "name": "workspace.patch",
            "arguments": {
                "workspace_id": ws.id,
                "subpath": "src/code.py",
                "patch_content": "diff",
                "base_checksum": base_hash,
            },
        },
    )
    resp = server_ro.handle_request(req)
    assert resp is not None
    assert resp.result["isError"] is True
    assert "NOT_AUTHORIZED" in resp.result["content"][0]["text"]


def test_mcp_tool_call_principal_argument_cannot_spoof(mcp_fixture: Dict[str, Any]) -> None:
    server_mut = mcp_fixture["server_mut"]
    ws = mcp_fixture["ws"]
    sample_file = mcp_fixture["sample_file"]
    base_hash = hashlib.sha256(sample_file.read_bytes()).hexdigest()

    diff = "--- a/src/code.py\n+++ b/src/code.py\n@@ -1,2 +1,2 @@\n-a = 1\n+a = 10\n b = 2\n"
    diff_hash = hashlib.sha256(diff.encode("utf-8")).hexdigest()

    # Create ticket specifically for spoofed principal
    appr_engine = ApprovalEngine(mcp_fixture["db"])
    ticket = appr_engine.create_ticket(
        principal_id="spoofed_admin",
        action_type="workspace.patch",
        workspace_id=ws.id,
        target_path="src/code.py",
        patch_hash=diff_hash,
    )
    appr_engine.approve(ticket.token)

    # Calling tool passing arguments["principal_id"] = "spoofed_admin"
    # should fail because connection principal is "mcp-client", not "spoofed_admin"
    req = McpRequest(
        id=14,
        method="tools/call",
        params={
            "name": "workspace.patch",
            "arguments": {
                "workspace_id": ws.id,
                "subpath": "src/code.py",
                "patch_content": diff,
                "base_checksum": base_hash,
                "dry_run": False,
                "approval_token": ticket.token,
                "principal_id": "spoofed_admin",
            },
        },
    )
    resp = server_mut.handle_request(req)
    assert resp is not None
    assert resp.result["isError"] is True
    assert "Approval principal mismatch" in resp.result["content"][0]["text"]
