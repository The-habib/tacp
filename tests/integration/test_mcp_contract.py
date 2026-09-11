"""Tests for MCP Protocol and Stdio Server Loop (Category F)."""

import io
import json
from typing import Any, Dict

from tacp.access.mcp.protocol import METHOD_NOT_FOUND, McpRequest
from tacp.access.mcp.server import MCP_PROTOCOL_VERSION, McpServer


def test_mcp_initialize(test_services: Dict[str, Any]) -> None:
    server: McpServer = test_services["mcp_server"]
    req = McpRequest(method="initialize", params={}, id=1)
    resp = server.handle_request(req)

    assert resp is not None
    assert resp.id == 1
    assert resp.error is None
    assert isinstance(resp.result, dict)
    assert resp.result["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert resp.result["serverInfo"]["name"] == "tacp"
    assert resp.result["serverInfo"]["version"] == "0.1.0-rc.1"
    assert "tools" in resp.result["capabilities"]


def test_mcp_initialized_notification(test_services: Dict[str, Any]) -> None:
    server: McpServer = test_services["mcp_server"]
    req = McpRequest(
        method="notifications/initialized",
        params={},
        id=None,
        is_notification=True,
    )
    resp = server.handle_request(req)
    assert resp is None


def test_mcp_ping(test_services: Dict[str, Any]) -> None:
    server: McpServer = test_services["mcp_server"]
    req = McpRequest(method="ping", params={}, id=2)
    resp = server.handle_request(req)
    assert resp is not None
    assert resp.id == 2
    assert resp.result == {}


def test_mcp_tools_list_all_13(test_services: Dict[str, Any]) -> None:
    server: McpServer = test_services["mcp_server"]
    req = McpRequest(method="tools/list", params={}, id=3)
    resp = server.handle_request(req)

    assert resp is not None
    assert isinstance(resp.result, dict)
    tools = resp.result["tools"]
    assert len(tools) == 13

    tool_names = {t["name"] for t in tools}
    expected_names = {
        "system.inspect",
        "system.health",
        "system.version",
        "capabilities.list",
        "workspace.list",
        "workspace.inspect",
        "fs.list",
        "fs.stat",
        "fs.read",
        "fs.search",
        "process.list",
        "process.inspect",
        "audit.recent",
    }
    assert tool_names == expected_names

    for t in tools:
        assert "description" in t
        assert "inputSchema" in t


def test_mcp_call_system_version(test_services: Dict[str, Any]) -> None:
    server: McpServer = test_services["mcp_server"]
    req = McpRequest(
        method="tools/call",
        params={"name": "system.version", "arguments": {}},
        id=4,
    )
    resp = server.handle_request(req)
    assert resp is not None
    assert isinstance(resp.result, dict)
    assert resp.result["isError"] is False
    content = json.loads(resp.result["content"][0]["text"])
    assert content["tacp_version"] == "0.1.0-rc.1"
    assert content["mcp_protocol_version"] == "2026-07-28"


def test_mcp_call_fs_read(test_services: Dict[str, Any]) -> None:
    server: McpServer = test_services["mcp_server"]
    ws = test_services["workspace"]
    req = McpRequest(
        method="tools/call",
        params={
            "name": "fs.read",
            "arguments": {"workspace_id": ws.id, "subpath": "hello.txt"},
        },
        id=5,
    )
    resp = server.handle_request(req)
    assert resp is not None
    assert isinstance(resp.result, dict)
    assert resp.result["isError"] is False
    content = json.loads(resp.result["content"][0]["text"])
    assert "Hello TACP World!" in content["content"]


def test_mcp_call_fs_read_underscore_normalized(test_services: Dict[str, Any]) -> None:
    server: McpServer = test_services["mcp_server"]
    ws = test_services["workspace"]
    req = McpRequest(
        method="tools/call",
        params={
            "name": "fs_read",
            "arguments": {"workspace_id": ws.id, "subpath": "hello.txt"},
        },
        id=6,
    )
    resp = server.handle_request(req)
    assert resp is not None
    assert isinstance(resp.result, dict)
    assert resp.result["isError"] is False


def test_mcp_call_outside_path_returns_error(test_services: Dict[str, Any]) -> None:
    server: McpServer = test_services["mcp_server"]
    ws = test_services["workspace"]
    req = McpRequest(
        method="tools/call",
        params={
            "name": "fs.read",
            "arguments": {"workspace_id": ws.id, "subpath": "../../etc/shadow"},
        },
        id=7,
    )
    resp = server.handle_request(req)
    assert resp is not None
    assert isinstance(resp.result, dict)
    assert resp.result["isError"] is True
    assert "OUTSIDE_WORKSPACE" in resp.result["content"][0]["text"]


def test_mcp_call_unknown_tool_returns_error(test_services: Dict[str, Any]) -> None:
    server: McpServer = test_services["mcp_server"]
    req = McpRequest(
        method="tools/call",
        params={"name": "forbidden.exec", "arguments": {}},
        id=8,
    )
    resp = server.handle_request(req)
    assert resp is not None
    assert isinstance(resp.result, dict)
    assert resp.result["isError"] is True


def test_mcp_unknown_method_returns_32601(test_services: Dict[str, Any]) -> None:
    server: McpServer = test_services["mcp_server"]
    req = McpRequest(method="unknown/method", params={}, id=9)
    resp = server.handle_request(req)
    assert resp is not None
    assert isinstance(resp.error, dict)
    assert resp.error["code"] == METHOD_NOT_FOUND


def test_mcp_stdio_stream_roundtrip(test_services: Dict[str, Any]) -> None:
    server: McpServer = test_services["mcp_server"]
    incoming = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}})
        + "\n"
        + json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "system.version", "arguments": {}},
            }
        )
        + "\n"
    )
    reader = io.StringIO(incoming)
    writer = io.StringIO()

    server.run_stdio(reader=reader, writer=writer)

    lines = [line for line in writer.getvalue().strip().split("\n") if line]
    assert len(lines) == 2

    resp1 = json.loads(lines[0])
    assert resp1["id"] == 1
    assert resp1["result"] == {}

    resp2 = json.loads(lines[1])
    assert resp2["id"] == 2
    assert resp2["result"]["isError"] is False


def test_mcp_server_discover(test_services: Dict[str, Any]) -> None:
    server: McpServer = test_services["mcp_server"]
    req = McpRequest(method="server/discover", params={}, id="disc-1")
    resp = server.handle_request(req)

    assert resp is not None
    assert resp.id == "disc-1"
    assert resp.error is None
    assert isinstance(resp.result, dict)
    assert "2026-07-28" in resp.result["supportedVersions"]
    assert "2024-11-05" in resp.result["supportedVersions"]
    assert "tools" in resp.result["capabilities"]
    assert resp.result["cacheScope"] == "public"
    assert resp.result["ttlMs"] == 60000
    assert resp.result["resultType"] == "complete"
    assert "strictly read-only" in resp.result["instructions"]


def test_mcp_initialize_negotiation(test_services: Dict[str, Any]) -> None:
    server: McpServer = test_services["mcp_server"]

    # Test client requesting modern 2026-07-28
    req_modern = McpRequest(
        method="initialize",
        params={"protocolVersion": "2026-07-28"},
        id=10,
    )
    resp_modern = server.handle_request(req_modern)
    assert resp_modern is not None
    assert resp_modern.result is not None
    assert resp_modern.result["protocolVersion"] == "2026-07-28"

    # Test client requesting 2025-11-25
    req_2025 = McpRequest(
        method="initialize",
        params={"protocolVersion": "2025-11-25"},
        id=11,
    )
    resp_2025 = server.handle_request(req_2025)
    assert resp_2025 is not None
    assert resp_2025.result is not None
    assert resp_2025.result["protocolVersion"] == "2025-11-25"

    # Test client requesting legacy 2024-11-05
    req_legacy = McpRequest(
        method="initialize",
        params={"protocolVersion": "2024-11-05"},
        id=12,
    )
    resp_legacy = server.handle_request(req_legacy)
    assert resp_legacy is not None
    assert resp_legacy.result is not None
    assert resp_legacy.result["protocolVersion"] == "2024-11-05"


def test_mcp_tools_list_modern_metadata(test_services: Dict[str, Any]) -> None:
    server: McpServer = test_services["mcp_server"]
    req = McpRequest(method="tools/list", params={}, id="list-1")
    resp = server.handle_request(req)

    assert resp is not None
    assert resp.result is not None
    assert resp.result["cacheScope"] == "public"
    assert resp.result["ttlMs"] == 60000
    assert resp.result["resultType"] == "complete"
    assert len(resp.result["tools"]) == 13


def test_mcp_tools_call_with_meta(test_services: Dict[str, Any]) -> None:
    server: McpServer = test_services["mcp_server"]
    req = McpRequest(
        method="tools/call",
        params={
            "name": "system.version",
            "arguments": {},
            "_meta": {"progressToken": "tok-123", "clientTraceId": "trace-abc"},
        },
        id="call-meta",
    )
    resp = server.handle_request(req)
    assert resp is not None
    assert resp.result is not None
    assert resp.result["isError"] is False
    assert resp.result["resultType"] == "complete"


def test_mcp_tools_call_invalid_meta(test_services: Dict[str, Any]) -> None:
    server: McpServer = test_services["mcp_server"]
    req = McpRequest(
        method="tools/call",
        params={
            "name": "system.version",
            "arguments": {},
            "_meta": "not-an-object",
        },
        id="call-bad-meta",
    )
    resp = server.handle_request(req)
    assert resp is not None
    assert resp.error is not None
    assert resp.error["code"] == -32602


def test_mcp_stateless_execution(test_services: Dict[str, Any]) -> None:
    """Verify modern MCP clients can list and call tools without prior handshake."""
    server: McpServer = test_services["mcp_server"]
    # Direct list
    resp_list = server.handle_request(McpRequest(method="tools/list", params={}, id=100))
    assert resp_list is not None
    assert resp_list.result is not None
    assert len(resp_list.result["tools"]) == 13

    # Direct call
    resp_call = server.handle_request(
        McpRequest(
            method="tools/call",
            params={"name": "capabilities.list", "arguments": {}},
            id=101,
        )
    )
    assert resp_call is not None
    assert resp_call.result is not None
    assert resp_call.result["isError"] is False
