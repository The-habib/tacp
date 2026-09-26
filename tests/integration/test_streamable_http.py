"""Integration tests for Streamable HTTP MCP transport."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Generator

import pytest

from tacp.access.mcp.transports.streamable_http import StreamableMcpServer
from tacp.control.auth import (
    SCOPE_ADMIN,
    SCOPE_FILES_READ,
    SCOPE_READ,
    TokenService,
)
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database


@pytest.fixture
def running_http_server(
    test_config: TacpConfig,
    test_db: Database,
    test_services: dict,
) -> Generator[tuple[str, TokenService, str], None, None]:
    token_service = TokenService(test_db)
    _, valid_token = token_service.create_token(
        name="Test Integration Token",
        scopes=[SCOPE_READ, SCOPE_FILES_READ, SCOPE_ADMIN],
    )

    test_services["policy_engine"].remote_enabled = True
    mcp_server = test_services["mcp_server"]

    # Bind to port 0 for dynamic ephemeral port allocation
    server = StreamableMcpServer(
        ("127.0.0.1", 0),
        mcp_server=mcp_server,
        token_service=token_service,
        auth_required=True,
    )
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield base_url, token_service, valid_token

    server.shutdown()
    server.server_close()


def test_health_and_readiness_endpoints(running_http_server: tuple[str, TokenService, str]) -> None:
    base_url, _, _ = running_http_server

    # Health check is unauthenticated
    req = urllib.request.Request(f"{base_url}/health")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "ok"

    # Readiness check is unauthenticated
    req_ready = urllib.request.Request(f"{base_url}/ready")
    with urllib.request.urlopen(req_ready) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["ready"] is True
        assert data["database"] is True


def test_unauthenticated_post_rejected(running_http_server: tuple[str, TokenService, str]) -> None:
    base_url, _, _ = running_http_server

    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/mcp",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)

    assert exc_info.value.code == 401
    err_body = json.loads(exc_info.value.read().decode("utf-8"))
    assert err_body["error"]["code"] == -32001
    assert "Unauthorized" in err_body["error"]["message"]


def test_invalid_bearer_token_rejected(running_http_server: tuple[str, TokenService, str]) -> None:
    base_url, _, _ = running_http_server

    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/mcp",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer tacp_sec_bogusinvalidtoken000000000000",
        },
        method="POST",
    )

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)

    assert exc_info.value.code == 401


def test_authenticated_mcp_initialize_and_tools_list(
    running_http_server: tuple[str, TokenService, str]
) -> None:
    base_url, _, valid_token = running_http_server

    # 1. Initialize
    init_payload = json.dumps({
        "jsonrpc": "2.0",
        "id": "req-init",
        "method": "initialize",
        "params": {
            "protocolVersion": "2026-07-28",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }).encode("utf-8")

    req_init = urllib.request.Request(
        f"{base_url}/mcp",
        data=init_payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {valid_token}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req_init) as resp:
        assert resp.status == 200
        assert resp.headers.get("Mcp-Session-Id") is not None
        body = json.loads(resp.read().decode("utf-8"))
        assert body["id"] == "req-init"
        assert body["result"]["protocolVersion"] == "2026-07-28"
        assert body["result"]["serverInfo"]["name"] == "tacp"

    # 2. tools/list
    list_payload = json.dumps({
        "jsonrpc": "2.0",
        "id": "req-list",
        "method": "tools/list",
        "params": {},
    }).encode("utf-8")

    req_list = urllib.request.Request(
        f"{base_url}/mcp",
        data=list_payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {valid_token}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req_list) as resp:
        assert resp.status == 200
        body = json.loads(resp.read().decode("utf-8"))
        assert body["id"] == "req-list"
        tool_names = [t["name"] for t in body["result"]["tools"]]
        assert "system.inspect" in tool_names
        assert "workspace.list" in tool_names


def test_authenticated_tool_call(running_http_server: tuple[str, TokenService, str]) -> None:
    base_url, _, valid_token = running_http_server

    call_payload = json.dumps({
        "jsonrpc": "2.0",
        "id": "req-call",
        "method": "tools/call",
        "params": {
            "name": "system.inspect",
            "arguments": {},
        },
    }).encode("utf-8")

    req_call = urllib.request.Request(
        f"{base_url}/mcp",
        data=call_payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {valid_token}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req_call) as resp:
        assert resp.status == 200
        body = json.loads(resp.read().decode("utf-8"))
        assert body["id"] == "req-call"
        assert body["result"]["isError"] is False
        content_text = body["result"]["content"][0]["text"]
        result_data = json.loads(content_text)
        assert "python_version" in result_data or "os" in result_data


def test_sse_streaming_response(running_http_server: tuple[str, TokenService, str]) -> None:
    base_url, _, valid_token = running_http_server

    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": "req-sse",
        "method": "tools/list",
        "params": {},
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/mcp",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {valid_token}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        assert "text/event-stream" in resp.headers.get("Content-Type", "")
        raw_text = resp.read().decode("utf-8")
        assert "event: message" in raw_text
        assert "tools" in raw_text


def test_session_id_tracking(running_http_server: tuple[str, TokenService, str]) -> None:
    base_url, _, valid_token = running_http_server

    custom_session = "custom-mcp-session-xyz-123"
    payload = json.dumps({"jsonrpc": "2.0", "id": "s-1", "method": "tools/list", "params": {}}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/mcp",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {valid_token}",
            "Mcp-Session-Id": custom_session,
        },
        method="POST",
    )

    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        assert resp.headers.get("Mcp-Session-Id") == custom_session


def test_read_only_token_cannot_mutate(
    running_http_server: tuple[str, TokenService, str],
    test_services: dict,
) -> None:
    base_url, token_service, _ = running_http_server

    # Create a token strictly limited to tacp.read
    _, ro_token = token_service.create_token(
        name="Read-Only Agent",
        scopes=[SCOPE_READ],
    )

    call_payload = json.dumps({
        "jsonrpc": "2.0",
        "id": "req-mutate",
        "method": "tools/call",
        "params": {
            "name": "workspace.patch",
            "arguments": {
                "workspace_id": test_services["workspace"].id,
                "relative_path": "hello.txt",
                "hunks": [],
            },
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/mcp",
        data=call_payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {ro_token}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        body = json.loads(resp.read().decode("utf-8"))
        assert body["id"] == "req-mutate"
        # Tool call should return error indicating lack of mutation permissions
        assert body["result"]["isError"] is True

