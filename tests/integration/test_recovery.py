"""Tests for TACP System Recovery, Persistence, and State Continuity (Category K)."""

from __future__ import annotations

from pathlib import Path

from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import create_mcp_server
from tacp.core.audit_service import AuditService
from tacp.core.workspace_service import WorkspaceService
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database


def test_recovery_lifecycle_and_audit_continuity(tmp_path: Path) -> None:
    """Verify state persistence and cryptographic hash chain integrity across server restarts."""
    data_dir = tmp_path / "recovery_data"
    ws_dir = tmp_path / "recovery_ws"
    ws_dir.mkdir(parents=True)
    (ws_dir / "app.py").write_text("print('version 1')")

    config = TacpConfig(
        data_dir=data_dir,
        db_path=data_dir / "persist.db",
        read_only=True,
        allowed_workspace_roots=[ws_dir],
    )

    # 1. First Lifecycle Session: create server, register workspace, make calls
    server1 = create_mcp_server(config)
    ws_service1 = WorkspaceService(Database(config.db_path))
    registered = ws_service1.register_workspace("test-ws", ws_dir)

    # Make multiple tool calls
    req1 = McpRequest(
        method="tools/call",
        params={
            "name": "fs.read",
            "arguments": {"workspace_id": registered.id, "subpath": "app.py"},
        },
        id=1,
    )
    resp1 = server1.handle_request(req1)
    assert resp1 is not None
    assert resp1.result is not None
    assert resp1.result["isError"] is False

    req2 = McpRequest(
        method="tools/call",
        params={"name": "fs.list", "arguments": {"workspace_id": registered.id, "subpath": ""}},
        id=2,
    )
    resp2 = server1.handle_request(req2)
    assert resp2 is not None
    assert resp2.result is not None
    assert resp2.result["isError"] is False

    # Simulate shutdown / crash: close all references
    del server1
    del ws_service1

    # 2. Second Lifecycle Session: start brand new server on same database
    server2 = create_mcp_server(config)
    db2 = Database(config.db_path)
    audit2 = AuditService(db2)
    ws_service2 = WorkspaceService(db2)

    # Verify workspace persisted
    persisted_ws = ws_service2.get_workspace(registered.id)
    assert persisted_ws.name == "test-ws"
    assert persisted_ws.root_path == ws_dir.resolve()

    # Verify audit trail persisted and cryptographic hash chain is valid
    recent_events = audit2.get_recent_events(limit=10)
    assert len(recent_events) >= 2
    assert audit2.verify_integrity() is True

    # Execute another call in new session and verify chain continues cleanly
    req3 = McpRequest(
        method="tools/call",
        params={"name": "system.version", "arguments": {}},
        id=3,
    )
    resp3 = server2.handle_request(req3)
    assert resp3 is not None
    assert resp3.result is not None
    assert resp3.result["isError"] is False

    # Audit chain must remain 100% valid after new entries
    assert audit2.verify_integrity() is True


def test_recovery_when_workspace_root_deleted_offline(tmp_path: Path) -> None:
    """Verify system handles missing workspace root gracefully if deleted while offline."""
    data_dir = tmp_path / "deleted_root_data"
    ws_dir = tmp_path / "ephemeral_ws"
    ws_dir.mkdir(parents=True)
    (ws_dir / "temp.txt").write_text("ephemeral")

    config = TacpConfig(
        data_dir=data_dir,
        db_path=data_dir / "ephemeral.db",
        read_only=True,
        allowed_workspace_roots=[ws_dir],
    )

    # Register workspace
    ws_service = WorkspaceService(Database(config.db_path))
    registered = ws_service.register_workspace("ephemeral-ws", ws_dir)

    # Delete workspace root directory from disk while server is not running
    import shutil

    shutil.rmtree(ws_dir)
    assert not ws_dir.exists()

    # Start new server session
    server = create_mcp_server(config)

    # Tool call on removed workspace directory must return structured error, not crash
    req = McpRequest(
        method="tools/call",
        params={"name": "fs.list", "arguments": {"workspace_id": registered.id, "subpath": ""}},
        id="del-test",
    )
    resp = server.handle_request(req)
    assert resp is not None
    assert resp.result is not None
    assert resp.result["isError"] is True
    assert "NOT_FOUND" in resp.result["content"][0]["text"]
