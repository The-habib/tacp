"""JSON-RPC 2.0 protocol definitions for MCP."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class McpProtocolError(Exception):
    """Raised when an MCP protocol violation occurs."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            result["data"] = self.data
        return result


# Standard JSON-RPC 2.0 error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


@dataclass
class McpRequest:
    """Represents an incoming JSON-RPC 2.0 request or notification."""

    method: str
    params: dict[str, Any]
    id: str | int | None = None
    is_notification: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> McpRequest:
        if not isinstance(data, dict):
            raise McpProtocolError(INVALID_REQUEST, "Payload must be a JSON object")

        if data.get("jsonrpc") != "2.0":
            raise McpProtocolError(
                INVALID_REQUEST, "Invalid or missing jsonrpc version (must be '2.0')"
            )

        if "method" not in data or not isinstance(data["method"], str):
            raise McpProtocolError(INVALID_REQUEST, "Missing or invalid 'method' field")

        method = data["method"]
        params = data.get("params", {})
        if not isinstance(params, dict):
            raise McpProtocolError(INVALID_PARAMS, "Expected object params")

        msg_id = data.get("id")
        is_notification = "id" not in data

        return cls(method=method, params=params, id=msg_id, is_notification=is_notification)


@dataclass
class McpResponse:
    """Represents an outgoing JSON-RPC 2.0 response."""

    id: str | int | None
    result: Any | None = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": self.id}
        if self.error is not None:
            payload["error"] = self.error
        else:
            payload["result"] = self.result if self.result is not None else {}
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))


def parse_message(raw_line: str) -> McpRequest:
    """Parse a single JSON-RPC line into an McpRequest."""
    trimmed = raw_line.strip()
    if not trimmed:
        raise McpProtocolError(PARSE_ERROR, "Empty message line")
    try:
        data = json.loads(trimmed)
    except json.JSONDecodeError as exc:
        raise McpProtocolError(PARSE_ERROR, f"JSON parse error: {exc}") from exc

    return McpRequest.from_dict(data)
