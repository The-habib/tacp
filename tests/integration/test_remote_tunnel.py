"""Integration and resilience tests for Phase 6.5: Remote Tunnel & REMOTE_AI Identity.

Verifies:
1. CLI `tacp remote status` command output, configuration display, and key masking.
2. CLI `tacp doctor` output with tunnel-client diagnostic checks.
3. MCP JSON-RPC protocol handshake (initialize, ping, tools/list) in remote mode.
4. End-to-end read-only tool calls executed by REMOTE_AI principal.
5. Audit trail records REMOTE_AI identity and maintains cryptographically valid hash chains.
6. Server restart resilience: database WAL and audit hash chain integrity preserved.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import create_mcp_server
from tacp.cli.main import main
from tacp.control.identity import Principal
from tacp.infrastructure.config import TacpConfig


def test_cli_remote_status_default(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify `tacp remote status` displays safe default unconfigured state."""
    tacp_dir = tmp_path / "tacp_remote_status_def"
    env = {
        "TACP_DATA_DIR": str(tacp_dir),
        "TACP_REMOTE_ENABLED": "false",
        "TACP_TRUST_PROFILE": "REMOTE_READ_ONLY",
        "CONTROL_PLANE_TUNNEL_ID": "",
        "CONTROL_PLANE_API_KEY": "",
    }
    with patch.dict(os.environ, env):
        code = main(["remote", "status"])
        assert code == 0
        captured = capsys.readouterr()
        assert "TACP Remote Integration Status" in captured.out
        assert "Remote Enabled     : False" in captured.out
        assert "Remote Read-Only   : True" in captured.out
        assert "Remote Mutation    : False" in captured.out
        assert "Remote Execution   : False" in captured.out
        assert "Trust Profile      : REMOTE_READ_ONLY" in captured.out


def test_cli_remote_status_configured(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify `tacp remote status` properly reflects active tunnel configuration and masks keys."""
    tacp_dir = tmp_path / "tacp_remote_status_cfg"
    env = {
        "TACP_DATA_DIR": str(tacp_dir),
        "TACP_REMOTE_ENABLED": "true",
        "CONTROL_PLANE_TUNNEL_ID": "tun_openai_prod_998877",
        "CONTROL_PLANE_API_KEY": "cp_live_secret_key_abcdef1234567890",
    }
    with patch.dict(os.environ, env):
        code = main(["remote", "status"])
        assert code == 0
        captured = capsys.readouterr()
        assert "Remote Enabled     : True" in captured.out
        assert "Tunnel ID          : tun_openai_prod_998877" in captured.out
        # Invariant: Full API key must NEVER be printed
        assert "cp_live_secret_key_abcdef1234567890" not in captured.out
        assert "CONFIGURED (hidden)" in captured.out


def test_cli_doctor_remote_checks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Verify `tacp doctor` includes tunnel client checks."""
    tacp_dir = tmp_path / "tacp_doctor_remote"
    with patch.dict(os.environ, {"TACP_DATA_DIR": str(tacp_dir)}):
        code = main(["doctor"])
        assert code == 0
        captured = capsys.readouterr()
        assert "OpenAI Tunnel Client" in captured.out
        assert "Remote Tunnel Governance" in captured.out


def test_mcp_handshake_remote_mode(tmp_path: Path) -> None:
    """Verify MCP protocol handshake in REMOTE_READ_ONLY mode."""
    cfg = TacpConfig(
        data_dir=tmp_path / "tacp_hs",
        db_path=tmp_path / "tacp_hs.db",
        read_only=True,
        trust_profile="REMOTE_READ_ONLY",
        remote_enabled=True,
        remote_read_only=True,
    )
    server = create_mcp_server(cfg)

    # 1. initialize
    init_req = McpRequest(
        id=1,
        method="initialize",
        params={
            "protocolVersion": "2026-07-28",
            "clientInfo": {"name": "ChatGPT-Secure-Tunnel", "version": "1.0"},
            "capabilities": {},
        },
    )
    init_resp = server.handle_request(init_req)
    assert init_resp is not None
    assert init_resp.result is not None
    assert init_resp.result["protocolVersion"] == "2026-07-28"
    assert init_resp.result["serverInfo"]["name"] == "tacp"

    # 2. ping
    ping_req = McpRequest(id=2, method="ping", params={})
    ping_resp = server.handle_request(ping_req)
    assert ping_resp is not None
    assert ping_resp.result == {}

    # 3. tools/list
    list_req = McpRequest(id=3, method="tools/list", params={})
    list_resp = server.handle_request(list_req)
    assert list_resp is not None
    assert list_resp.result is not None
    tools = list_resp.result["tools"]
    tool_names = {t["name"] for t in tools}

    assert len(tools) == 13
    assert "workspace.patch" not in tool_names
    assert "execution.request" not in tool_names
    assert "system.inspect" in tool_names
    assert "fs.read" in tool_names


def test_mcp_remote_ai_tool_call_roundtrip(tmp_path: Path) -> None:
    """Verify REMOTE_AI principal can execute read-only tools and receives structured responses."""
    ws_dir = tmp_path / "remote_project"
    ws_dir.mkdir()
    (ws_dir / "app.py").write_text("print('hello world')\n")

    cfg = TacpConfig(
        data_dir=tmp_path / "tacp_rtt",
        db_path=tmp_path / "tacp_rtt.db",
        read_only=True,
        trust_profile="REMOTE_READ_ONLY",
        remote_enabled=True,
        remote_read_only=True,
    )
    server = create_mcp_server(cfg)
    ws = server.tool_registry.workspace_service.register_workspace("remote-ws", ws_dir)

    remote_principal = Principal.remote_ai("chatgpt-session-42")

    # 1. system.version
    res_ver = server.tool_registry.execute_tool(
        "system.version",
        arguments={},
        principal=remote_principal,
        request_id="req-1",
    )
    assert "tacp_version" in res_ver
    assert res_ver["mcp_protocol_version"] == "2026-07-28"

    # 2. fs.read
    res_read = server.tool_registry.execute_tool(
        "fs.read",
        arguments={"workspace_id": ws.id, "subpath": "app.py"},
        principal=remote_principal,
        request_id="req-2",
    )
    assert "print('hello world')" in res_read["content"]

    # 3. workspace.list
    res_ws = server.tool_registry.execute_tool(
        "workspace.list",
        arguments={},
        principal=remote_principal,
        request_id="req-3",
    )
    assert len(res_ws["workspaces"]) >= 1

    # 4. process.list
    res_proc = server.tool_registry.execute_tool(
        "process.list",
        arguments={},
        principal=remote_principal,
        request_id="req-4",
    )
    assert "processes" in res_proc


def test_audit_hash_chain_and_restart_resilience(tmp_path: Path) -> None:
    """Verify audit log records REMOTE_AI principal and hash chain survives server restart."""
    db_path = tmp_path / "resilience.db"
    data_dir = tmp_path / "resilience_data"
    data_dir.mkdir()

    cfg = TacpConfig(
        data_dir=data_dir,
        db_path=db_path,
        read_only=True,
        trust_profile="REMOTE_READ_ONLY",
        remote_enabled=True,
        remote_read_only=True,
    )

    # Session 1: initial operations
    server1 = create_mcp_server(cfg)
    remote_p = Principal.remote_ai("chatgpt-session-1")

    server1.tool_registry.execute_tool(
        "system.version",
        arguments={},
        principal=remote_p,
        request_id="req-s1-1",
    )
    server1.tool_registry.execute_tool(
        "system.health",
        arguments={},
        principal=remote_p,
        request_id="req-s1-2",
    )

    # Check audit events
    audit_svc1 = server1.tool_registry.audit_service
    events1 = audit_svc1.get_recent_events(limit=10)
    assert len(events1) >= 2
    for ev in events1:
        assert ev["principal"] == "chatgpt-session-1"

    # Verify SHA-256 chain integrity before shutdown
    integrity1 = audit_svc1.verify_integrity()
    assert integrity1 is True

    # Shutdown server1 (close DB)
    if hasattr(server1.tool_registry.workspace_service, "db"):
        server1.tool_registry.workspace_service.db.close()

    # Session 2: simulate restart / reconnect
    server2 = create_mcp_server(cfg)
    remote_p2 = Principal.remote_ai("chatgpt-session-2")

    server2.tool_registry.execute_tool(
        "system.inspect",
        arguments={},
        principal=remote_p2,
        request_id="req-s2-1",
    )

    audit_svc2 = server2.tool_registry.audit_service
    events2 = audit_svc2.get_recent_events(limit=10)
    assert len(events2) >= 3

    # Invariant: hash chain remains valid across server restart
    integrity2 = audit_svc2.verify_integrity()
    assert integrity2 is True
