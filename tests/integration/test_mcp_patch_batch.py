"""Integration tests for MCP access to workspace.patch_batch."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tacp.access.mcp.server import create_mcp_server
from tacp.control.approval import compute_canonical_batch_hash
from tacp.infrastructure.config import OutputLimits, TacpConfig


@pytest.fixture
def batch_config(tmp_path: Path) -> TacpConfig:
    data_dir = tmp_path / ".tacp"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "tacp.db"
    return TacpConfig(
        data_dir=data_dir,
        db_path=db_path,
        mutation_enabled=True,
        batch_mutation_enabled=True,
        read_only=False,
        limits=OutputLimits(
            max_batch_files=5,
            max_batch_patch_total_bytes=10000,
            max_batch_resulting_total_bytes=50000,
        ),
    )


def test_mcp_tools_list_conditionally_exposes_batch(tmp_path: Path) -> None:
    data_dir = tmp_path / ".tacp"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "tacp.db"

    # 1. Read-only (default): neither patch nor patch_batch
    cfg_ro = TacpConfig(data_dir=data_dir, db_path=db_path, mutation_enabled=False, read_only=True)
    server_ro = create_mcp_server(cfg_ro)
    tools_ro = server_ro.tool_registry.list_tools()
    tool_names_ro = {t["name"] for t in tools_ro}
    assert "workspace.patch" not in tool_names_ro
    assert "workspace.patch_batch" not in tool_names_ro

    # 2. Mutation enabled, batch mutation disabled: only workspace.patch
    cfg_mut = TacpConfig(
        data_dir=data_dir,
        db_path=db_path,
        mutation_enabled=True,
        batch_mutation_enabled=False,
        read_only=False,
    )
    server_mut = create_mcp_server(cfg_mut)
    tools_mut = server_mut.tool_registry.list_tools()
    tool_names_mut = {t["name"] for t in tools_mut}
    assert "workspace.patch" in tool_names_mut
    assert "workspace.patch_batch" not in tool_names_mut

    # 3. Both enabled: both workspace.patch and workspace.patch_batch exposed
    cfg_batch = TacpConfig(
        data_dir=data_dir,
        db_path=db_path,
        mutation_enabled=True,
        batch_mutation_enabled=True,
        read_only=False,
    )
    server_batch = create_mcp_server(cfg_batch)
    tools_batch = server_batch.tool_registry.list_tools()
    tool_names_batch = {t["name"] for t in tools_batch}
    assert "workspace.patch" in tool_names_batch
    assert "workspace.patch_batch" in tool_names_batch


def test_mcp_tools_call_batch_dry_run(batch_config: TacpConfig, tmp_path: Path) -> None:
    server = create_mcp_server(batch_config)
    ws_list = server.tool_registry.workspace_service.list_workspaces()
    ws_id = str(ws_list[0]["id"])
    ws_root = Path(str(ws_list[0]["root_path"]))

    f1 = ws_root / "t1.txt"
    f2 = ws_root / "t2.txt"
    f1.write_text("aaa\n")
    f2.write_text("bbb\n")

    c1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    c2 = hashlib.sha256(f2.read_bytes()).hexdigest()

    patches = [
        {
            "subpath": "t1.txt",
            "patch_content": "--- t1.txt\n+++ t1.txt\n@@ -1 +1 @@\n-aaa\n+AAA\n",
            "base_checksum": c1,
        },
        {
            "subpath": "t2.txt",
            "patch_content": "--- t2.txt\n+++ t2.txt\n@@ -1 +1 @@\n-bbb\n+BBB\n",
            "base_checksum": c2,
        },
    ]

    res = server.tool_registry.execute_tool(
        "workspace.patch_batch",
        arguments={
            "workspace_id": ws_id,
            "patches": patches,
            "dry_run": True,
        },
    )

    assert res["status"] == "SIMULATED"
    assert len(res["results"]) == 2
    assert f1.read_text() == "aaa\n"
    assert f2.read_text() == "bbb\n"


def test_mcp_tools_call_batch_live_with_approval(batch_config: TacpConfig, tmp_path: Path) -> None:
    server = create_mcp_server(batch_config)
    ws_list = server.tool_registry.workspace_service.list_workspaces()
    ws_id = str(ws_list[0]["id"])
    ws_root = Path(str(ws_list[0]["root_path"]))

    f1 = ws_root / "p1.txt"
    f2 = ws_root / "p2.txt"
    f1.write_text("hello 1\n")
    f2.write_text("hello 2\n")

    c1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    c2 = hashlib.sha256(f2.read_bytes()).hexdigest()

    patches = [
        {
            "subpath": "p1.txt",
            "patch_content": "--- p1.txt\n+++ p1.txt\n@@ -1 +1 @@\n-hello 1\n+bye 1\n",
            "base_checksum": c1,
        },
        {
            "subpath": "p2.txt",
            "patch_content": "--- p2.txt\n+++ p2.txt\n@@ -1 +1 @@\n-hello 2\n+bye 2\n",
            "base_checksum": c2,
        },
    ]

    # Without approval: should raise TacpApprovalRequiredError with ticket created
    try:
        server.tool_registry.execute_tool(
            "tacp_workspace_patch_batch",
            arguments={
                "workspace_id": ws_id,
                "patches": patches,
                "dry_run": False,
            },
        )
        pytest.fail("Expected approval required error")
    except Exception as exc:
        assert "requires explicit human approval" in str(exc)

    # Approve ticket
    patch_svc = server.tool_registry.patch_service
    assert patch_svc is not None
    batch_hash = compute_canonical_batch_hash(patches)
    ticket = patch_svc.approval_engine.create_ticket(
        principal_id="mcp-client",
        action_type="workspace.patch_batch",
        workspace_id=ws_id,
        target_path="*",
        patch_hash=batch_hash,
    )
    patch_svc.approval_engine.approve(ticket.token)

    # Execute with approval
    res = server.tool_registry.execute_tool(
        "workspace_patch_batch",
        arguments={
            "workspace_id": ws_id,
            "patches": patches,
            "dry_run": False,
            "approval_token": ticket.token,
        },
    )

    assert res["status"] == "APPLIED"
    assert len(res["results"]) == 2
    assert f1.read_text() == "bye 1\n"
    assert f2.read_text() == "bye 2\n"
