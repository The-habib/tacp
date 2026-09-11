"""Simulated OpenAI-compatible Agent Tunnel and Tool Calling Adapter Test.

Verifies end-to-end integration:
OpenAI Tool Call -> Adapter -> TACP MCP Server -> Translated Response.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from tacp import __version__
from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import McpServer


class OpenAiMcpAdapter:
    """Translates between OpenAI tool calling format and MCP JSON-RPC protocol."""

    @staticmethod
    def openai_to_mcp_request(openai_tool_call: Dict[str, Any]) -> McpRequest:
        call_id = openai_tool_call.get("id", "default_call_id")
        func = openai_tool_call.get("function", {})
        func_name = func.get("name", "")

        # Normalize underscore function name to MCP capability dot-notation
        mcp_tool_name = func_name.replace("_", ".", 1) if "_" in func_name else func_name

        raw_arguments = func.get("arguments", "{}")
        if isinstance(raw_arguments, str):
            try:
                args = json.loads(raw_arguments)
            except json.JSONDecodeError:
                args = {}
        elif isinstance(raw_arguments, dict):
            args = raw_arguments
        else:
            args = {}

        return McpRequest(
            method="tools/call",
            params={
                "name": mcp_tool_name,
                "arguments": args,
                "_meta": {"openai_call_id": call_id, "adapter": "tacp-openai-bridge-v1"},
            },
            id=call_id,
        )

    @staticmethod
    def mcp_response_to_openai_message(
        openai_tool_call: Dict[str, Any],
        mcp_resp: Any,
    ) -> Dict[str, Any]:
        call_id = openai_tool_call.get("id", "default_call_id")

        if mcp_resp.error:
            content_str = json.dumps({"error": mcp_resp.error})
        elif mcp_resp.result and "content" in mcp_resp.result:
            # Extract text parts
            parts = [item.get("text", "") for item in mcp_resp.result["content"]]
            content_str = "\n".join(parts)
        else:
            content_str = "{}"

        return {
            "role": "tool",
            "tool_call_id": call_id,
            "content": content_str,
        }


def test_openai_tool_call_roundtrip_success(test_services: Dict[str, Any]) -> None:
    """Verify standard OpenAI tool call to system.version runs cleanly through adapter."""
    server: McpServer = test_services["mcp_server"]
    adapter = OpenAiMcpAdapter()

    openai_call = {
        "id": "call_987xyz",
        "type": "function",
        "function": {
            "name": "system_version",
            "arguments": "{}",
        },
    }

    mcp_req = adapter.openai_to_mcp_request(openai_call)
    assert mcp_req.method == "tools/call"
    assert mcp_req.params["name"] == "system.version"
    assert mcp_req.params["_meta"]["openai_call_id"] == "call_987xyz"

    mcp_resp = server.handle_request(mcp_req)
    assert mcp_resp is not None
    assert mcp_resp.result is not None
    assert mcp_resp.result["isError"] is False

    openai_msg = adapter.mcp_response_to_openai_message(openai_call, mcp_resp)
    assert openai_msg["role"] == "tool"
    assert openai_msg["tool_call_id"] == "call_987xyz"

    parsed_content = json.loads(openai_msg["content"])
    assert parsed_content["tacp_version"] == __version__
    assert parsed_content["mode"] in ("READ_ONLY", "GOVERNED")


def test_openai_tool_call_fs_read_success(test_services: Dict[str, Any]) -> None:
    """Verify OpenAI tool call reading an authorized workspace file."""
    server: McpServer = test_services["mcp_server"]
    ws = test_services["workspace"]
    adapter = OpenAiMcpAdapter()

    openai_call = {
        "id": "call_fs_123",
        "type": "function",
        "function": {
            "name": "fs_read",
            "arguments": json.dumps({"workspace_id": ws.id, "subpath": "hello.txt"}),
        },
    }

    mcp_req = adapter.openai_to_mcp_request(openai_call)
    mcp_resp = server.handle_request(mcp_req)
    assert mcp_resp is not None
    assert mcp_resp.result is not None
    assert mcp_resp.result["isError"] is False

    openai_msg = adapter.mcp_response_to_openai_message(openai_call, mcp_resp)
    parsed = json.loads(openai_msg["content"])
    assert "Hello TACP World!" in parsed["content"]


def test_openai_tool_call_security_violation_handled(test_services: Dict[str, Any]) -> None:
    """Verify security violation returns structured error in OpenAI format without crashes."""
    server: McpServer = test_services["mcp_server"]
    ws = test_services["workspace"]
    adapter = OpenAiMcpAdapter()

    openai_call = {
        "id": "call_sec_456",
        "type": "function",
        "function": {
            "name": "fs_read",
            "arguments": json.dumps({"workspace_id": ws.id, "subpath": "../../../etc/passwd"}),
        },
    }

    mcp_req = adapter.openai_to_mcp_request(openai_call)
    mcp_resp = server.handle_request(mcp_req)
    assert mcp_resp is not None
    assert mcp_resp.result is not None
    assert mcp_resp.result["isError"] is True

    openai_msg = adapter.mcp_response_to_openai_message(openai_call, mcp_resp)
    assert "OUTSIDE_WORKSPACE" in openai_msg["content"]
    assert openai_msg["tool_call_id"] == "call_sec_456"


def test_openai_tool_call_malformed_arguments_handled(test_services: Dict[str, Any]) -> None:
    """Verify unparseable JSON argument strings are gracefully handled."""
    adapter = OpenAiMcpAdapter()
    openai_call = {
        "id": "call_bad_json",
        "type": "function",
        "function": {
            "name": "fs_read",
            "arguments": "{not-json",
        },
    }
    mcp_req = adapter.openai_to_mcp_request(openai_call)
    assert mcp_req.params["arguments"] == {}
