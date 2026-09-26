"""Unit and integration tests for TACP Device Control Plane."""

import json
from pathlib import Path
import pytest
from tacp.backends.base import BackendType, BackendStatus
from tacp.backends.manager import BackendManager
from tacp.backends.termux import TermuxBackend
from tacp.backends.android_shell import AndroidShellBackend
from tacp.backends.shizuku import ShizukuBackend
from tacp.backends.root import RootBackend
from tacp.backends.adb import AdbBackend
from tacp.backends.android_bridge import AndroidBridgeBackend
from tacp.backends.termux_api import TermuxApiBackend
from tacp.engine.capability import CapabilityDefinition
from tacp.engine.registry import CapabilityRegistry, default_registry
from tacp.engine.resolver import CapabilityResolver
from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import create_mcp_server
from tacp.infrastructure.config import OutputLimits, TacpConfig
from tacp.infrastructure.database import Database


def test_backends_registration_and_status():
    bm = BackendManager()
    info = bm.probe_all()
    assert len(info) == 7
    backend_names = list(info.keys())
    assert "termux" in backend_names
    assert "android_shell" in backend_names
    assert "termux_api" in backend_names
    assert "shizuku" in backend_names
    assert "root" in backend_names
    assert "adb" in backend_names
    assert "android_bridge" in backend_names


def test_backend_unfulfilled_requirements():
    shizuku = ShizukuBackend()
    shizuku.probe()
    if not shizuku.is_available:
        assert shizuku.status in (BackendStatus.SHIZUKU_REQUIRED, BackendStatus.UNAVAILABLE)
        assert len(shizuku.details) > 0


def test_capability_registry_counts_and_categories():
    reg = default_registry
    all_caps = reg.list_all()
    assert len(all_caps) >= 60

    # Ensure key device categories exist
    categories = {cap.category for cap in all_caps}
    assert "shell" in categories
    assert "process" in categories
    assert "filesystem" in categories
    assert "storage" in categories
    assert "device" in categories
    assert "package" in categories
    assert "network" in categories
    assert "automation" in categories
    assert "camera" in categories or "screen" in categories


def test_resolver_selection():
    bm = BackendManager()
    resolver = CapabilityResolver(bm)
    
    cap = default_registry.get("device.info")
    assert cap is not None
    backend, status, reason = resolver.resolve(cap)
    if backend:
        assert backend.name in ("termux", "android_shell")
        assert status == BackendStatus.AVAILABLE
    else:
        assert status != BackendStatus.AVAILABLE


def test_handlers_execution_live():
    reg = default_registry
    
    # 1. shell.pwd
    cap = reg.get("shell.pwd")
    assert cap is not None
    res = reg.dispatch("shell.pwd", {})
    assert res.get("success") is True
    assert "cwd" in res

    # 2. device.info
    res = reg.dispatch("device.info", {})
    assert res.get("success") is True
    assert "device" in res or "os" in res

    # 3. storage.overview
    res = reg.dispatch("storage.overview", {})
    assert res.get("success") is True
    assert "storage_roots" in res or "mounts" in res

    # 4. network.interfaces
    res = reg.dispatch("network.interfaces", {})
    assert res.get("success") is True
    assert "interfaces" in res

    # 5. package.list
    res = reg.dispatch("package.list", {"limit": 5})
    assert res.get("success") is True
    assert "packages" in res

    # 6. diagnostics.bundle
    res = reg.dispatch("diagnostics.bundle", {})
    assert res.get("success") is True
    assert "bundle_path" in res


def test_mcp_tools_list_flag(tmp_path: Path):
    db_path = tmp_path / "test_mcp.db"
    cfg = TacpConfig(
        data_dir=tmp_path / ".tacp",
        db_path=db_path,
        execution_enabled=True,
        read_only=False,
        limits=OutputLimits(),
    )
    # Server with device capabilities disabled
    server_disabled = create_mcp_server(config=cfg, enable_device_capabilities=False)
    req1 = McpRequest(id=1, method="tools/list", params={})
    resp1 = server_disabled.handle_request(req1)
    assert resp1 is not None
    base_count = len(resp1.result["tools"])

    # Server with device capabilities enabled
    server_enabled = create_mcp_server(config=cfg, enable_device_capabilities=True)
    req2 = McpRequest(id=2, method="tools/list", params={})
    resp2 = server_enabled.handle_request(req2)
    assert resp2 is not None
    dev_tools = default_registry.get_mcp_tools()
    expected_unique = len({t["name"] for t in resp1.result["tools"]}.union({t["name"] for t in dev_tools}))
    assert len(resp2.result["tools"]) == expected_unique
    tool_names = [t["name"] for t in resp2.result["tools"]]
    assert "device.info" in tool_names or "device_info" in tool_names
    assert "storage.overview" in tool_names or "storage_overview" in tool_names


def test_mcp_execute_device_tool(tmp_path: Path):
    db_path = tmp_path / "test_mcp_exec.db"
    cfg = TacpConfig(
        data_dir=tmp_path / ".tacp_exec",
        db_path=db_path,
        execution_enabled=True,
        read_only=False,
        limits=OutputLimits(),
    )
    server = create_mcp_server(config=cfg, enable_device_capabilities=True)
    req = McpRequest(
        id=10,
        method="tools/call",
        params={
            "name": "device.info",
            "arguments": {},
        },
    )
    resp = server.handle_request(req)
    assert resp is not None
    assert resp.result.get("isError") is not True
    content = resp.result["content"]
    assert len(content) >= 1
    assert "success" in content[0]["text"]


def test_mcp_server_resources_and_prompts(tmp_path: Path):
    db_path = tmp_path / "test_mcp_res.db"
    cfg = TacpConfig(
        data_dir=tmp_path / ".tacp_res",
        db_path=db_path,
        execution_enabled=True,
        read_only=False,
        limits=OutputLimits(),
    )
    server = create_mcp_server(config=cfg, enable_device_capabilities=True)
    
    # Check resources list
    res_list = server.handle_request(McpRequest(id=1, method="resources/list", params={}))
    assert res_list is not None
    resources = res_list.result["resources"]
    uris = [r["uri"] for r in resources]
    assert "tacp://device/info" in uris
    assert "tacp://capabilities/list" in uris

    # Check resource read
    res_read = server.handle_request(McpRequest(
        id=2,
        method="resources/read",
        params={"uri": "tacp://device/info"}
    ))
    assert res_read is not None
    contents = res_read.result["contents"]
    assert len(contents) == 1
    assert contents[0]["uri"] == "tacp://device/info"

    # Check prompts list
    p_list = server.handle_request(McpRequest(id=3, method="prompts/list", params={}))
    assert p_list is not None
    prompts = p_list.result["prompts"]
    p_names = [p["name"] for p in prompts]
    assert "device-diagnostics" in p_names
    assert "inspect-device" in p_names

    # Check prompt get
    p_get = server.handle_request(McpRequest(
        id=4,
        method="prompts/get",
        params={"name": "device-diagnostics", "arguments": {}}
    ))
    assert p_get is not None
    messages = p_get.result["messages"]
    assert len(messages) >= 1
    assert "diagnostics" in messages[0]["content"]["text"].lower()
