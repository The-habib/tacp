"""Streamable HTTP MCP Transport for TACP.

Conforms to the Model Context Protocol (MCP) Streamable HTTP transport specification.
Supports POST requests with JSON-RPC 2.0 payloads, optional SSE responses,
session correlation, Bearer token authentication, and health observability.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from tacp.access.mcp.server import McpServer
    from tacp.control.auth import TokenService

from tacp.access.mcp.protocol import (
    INTERNAL_ERROR,
    PARSE_ERROR,
    McpProtocolError,
    McpRequest,
    McpResponse,
)
from tacp.control.identity import Principal
from tacp.domain.audit import AuditEvent

logger = logging.getLogger(__name__)

UNAUTHORIZED_CODE = -32001
FORBIDDEN_CODE = -32003


class StreamableMcpHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler implementing MCP Streamable HTTP specification."""

    protocol_version = "HTTP/1.1"
    server: StreamableMcpServer

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS, HEAD")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, Mcp-Session-Id, Mcp-Protocol-Version, X-Request-ID",
        )
        self.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id, Mcp-Protocol-Version")

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests."""
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests for probes, metadata, and optional SSE channels."""
        path = self.path.split("?")[0]

        # Health endpoint (unauthenticated)
        if path in ("/health", "/healthz"):
            body = json.dumps(
                {"status": "ok", "version": self.server.mcp_server.config.version}
            ).encode("utf-8")
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Readiness endpoint
        if path in ("/ready", "/readyz"):
            db_ok = self.server.mcp_server.tool_registry.system_service.db.is_healthy()
            workspaces = len(
                self.server.mcp_server.tool_registry.workspace_service.list_workspaces()
            )
            body = json.dumps(
                {
                    "ready": db_ok,
                    "database": db_ok,
                    "workspaces": workspaces,
                    "transport": "streamable-http",
                }
            ).encode("utf-8")
            self.send_response(200 if db_ok else 503)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # OAuth metadata returns 404 when OAuth is not configured
        if ".well-known" in path:
            self.send_response(404)
            self.end_headers()
            return

        # Status endpoint (requires auth if auth is enabled)
        if path == "/status":
            principal = self._authenticate()
            if self.server.auth_required and not principal:
                self._send_unauthorized("Authentication required for /status")
                return
            health = self.server.mcp_server.tool_registry.system_service.get_health()
            info = self.server.mcp_server.tool_registry.system_service.inspect_system()
            body = json.dumps({"health": health, "system": info}).encode("utf-8")
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Primary MCP endpoint GET
        if path in ("/", "/mcp"):
            accept = self.headers.get("Accept", "")
            # If client requested Server-Sent Events via GET on Streamable HTTP endpoint
            if "text/event-stream" in accept:
                self.send_response(405)
                self._send_cors_headers()
                self.send_header("Allow", "POST, OPTIONS, HEAD")
                self.end_headers()
                return

            # Default JSON metadata
            body = json.dumps(
                {
                    "name": "tacp",
                    "version": self.server.mcp_server.config.version,
                    "protocolVersion": "2026-07-28",
                    "transport": "streamable-http",
                    "auth_required": self.server.auth_required,
                    "endpoint": "/mcp",
                }
            ).encode("utf-8")
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        """Handle POST requests for MCP tool calls and JSON-RPC dispatch."""
        path = self.path.split("?")[0]
        if path not in ("/", "/mcp"):
            self.send_response(404)
            self.end_headers()
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            content_length = 0

        # Enforce max body size (10MB limit)
        if content_length > 10 * 1024 * 1024:
            self.send_response(413)
            self.end_headers()
            return

        # 1. Authenticate if required
        principal = self._authenticate()
        if self.server.auth_required and not principal:
            if content_length > 0:
                try:
                    self.rfile.read(content_length)
                except Exception:
                    pass
            self._send_unauthorized()
            return

        if content_length <= 0:
            # Empty probe returns ok
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}\n')
            return

        raw_body = self.rfile.read(content_length).decode("utf-8")
        if not raw_body.strip():
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}\n')
            return

        session_id = self._get_or_create_session()
        accept_header = self.headers.get("Accept", "")
        stream_mode = "text/event-stream" in accept_header

        # 3. Parse JSON-RPC message (handle single or batch)
        try:
            parsed_json = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            err_resp = McpResponse(
                id=None, error={"code": PARSE_ERROR, "message": f"Parse error: {exc}"}
            )
            self._send_response_body(err_resp.to_json().encode("utf-8"), session_id=session_id)
            return

        is_batch = isinstance(parsed_json, list)
        items = parsed_json if is_batch else [parsed_json]

        responses: List[Dict[str, Any]] = []
        for item in items:
            try:
                req_obj = McpRequest.from_dict(item)
                # Inject authenticated principal into tool registry if calling tools
                resp = self._dispatch_with_principal(req_obj, principal)
                if resp is not None:
                    responses.append(resp.to_dict())
            except McpProtocolError as exc:
                responses.append(
                    McpResponse(
                        id=item.get("id") if isinstance(item, dict) else None, error=exc.to_dict()
                    ).to_dict()
                )
            except Exception as exc:
                responses.append(
                    McpResponse(
                        id=item.get("id") if isinstance(item, dict) else None,
                        error={"code": INTERNAL_ERROR, "message": str(exc)},
                    ).to_dict()
                )

        if not responses:
            # Notifications only
            self.send_response(204)
            self._send_cors_headers()
            self.send_header("Mcp-Session-Id", session_id)
            self.end_headers()
            return

        if stream_mode:
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Mcp-Session-Id", session_id)
            self.end_headers()
            for r in responses:
                chunk = f"event: message\ndata: {json.dumps(r)}\n\n"
                self.wfile.write(chunk.encode("utf-8"))
            self.wfile.flush()
            self.close_connection = True
        else:
            final_data = responses if is_batch else responses[0]
            body_bytes = json.dumps(final_data).encode("utf-8")
            self._send_response_body(body_bytes, session_id=session_id)

    def _dispatch_with_principal(
        self, request: McpRequest, principal: Optional[Principal]
    ) -> Optional[McpResponse]:
        """Dispatch an MCP request while binding the authenticated principal."""
        if request.method == "tools/call" and principal is not None:
            tool_name = str(request.params.get("name", ""))
            arguments = request.params.get("arguments", {})
            req_id = request.id
            _meta = request.params.get("_meta", {})
            correlation_id = _meta.get("requestId") or str(req_id)
            try:
                result = self.server.mcp_server.tool_registry.execute_tool(
                    tool_name,
                    arguments,
                    principal=principal,
                    request_id=correlation_id,
                )
                return McpResponse(
                    id=req_id,
                    result={
                        "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                        "isError": False,
                        "resultType": "complete",
                    },
                )
            except Exception as exc:
                err_text = f"Error: {exc}"
                return McpResponse(
                    id=req_id,
                    result={
                        "content": [{"type": "text", "text": err_text}],
                        "isError": True,
                        "resultType": "complete",
                    },
                )
        return self.server.mcp_server.handle_request(request)

    def _authenticate(self) -> Optional[Principal]:
        """Extract and validate Bearer token from Authorization header."""
        auth_header = self.headers.get("Authorization", "")
        if not auth_header:
            return None

        parts = auth_header.strip().split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None

        raw_token = parts[1].strip()
        if not self.server.token_service:
            # If no token service configured, accept any non-empty bearer token for testing
            return Principal.remote_ai(agent_id="remote_agent")

        token_record = self.server.token_service.validate_token(raw_token)
        if not token_record:
            # Record failed auth attempt in audit log
            try:
                self.server.mcp_server.tool_registry.audit_service.record_event(
                    AuditEvent(
                        capability="auth.verify",
                        action="authenticate",
                        policy_decision="DENY",
                        result="FAILED",
                        duration_ms=0,
                        principal="anonymous",
                        parameters_redacted={"reason": "invalid_or_revoked_token"},
                    )
                )
            except Exception:
                pass
            return None

        return self.server.token_service.principal_from_token(token_record)

    def _get_or_create_session(self) -> str:
        client_session = self.headers.get("Mcp-Session-Id")
        if client_session:
            return client_session.strip()
        return str(uuid.uuid4())

    def _send_response_body(self, body_bytes: bytes, session_id: Optional[str] = None) -> None:
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body_bytes)))
        if session_id:
            self.send_header("Mcp-Session-Id", session_id)
        self.end_headers()
        self.wfile.write(body_bytes)

    def _send_unauthorized(self, msg: str = "Unauthorized: valid Bearer token required") -> None:
        err_body = json.dumps(
            {
                "jsonrpc": "2.0",
                "error": {
                    "code": UNAUTHORIZED_CODE,
                    "message": msg,
                },
            }
        ).encode("utf-8")
        self.send_response(401)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("WWW-Authenticate", 'Bearer realm="TACP MCP"')
        self.send_header("Content-Length", str(len(err_body)))
        self.end_headers()
        self.wfile.write(err_body)

    def log_message(self, format: str, *args: object) -> None:
        # Route server logs safely to stderr
        sys.stderr.write(f"[Streamable-HTTP] {format % args}\n")


class StreamableMcpServer(ThreadingHTTPServer):
    """Threaded HTTP Server for MCP Streamable HTTP."""

    def __init__(
        self,
        server_address: tuple[str, int],
        mcp_server: McpServer,
        token_service: Optional[TokenService] = None,
        auth_required: bool = False,
    ) -> None:
        super().__init__(server_address, StreamableMcpHandler)
        self.mcp_server = mcp_server
        self.token_service = token_service
        self.auth_required = auth_required
        self.daemon_threads = True


def start_streamable_http_server(
    mcp_server: McpServer,
    host: str = "127.0.0.1",
    port: int = 8765,
    token_service: Optional[TokenService] = None,
    auth_required: bool = False,
) -> StreamableMcpServer:
    """Instantiate and start the Streamable HTTP MCP server in background or blocking."""
    httpd = StreamableMcpServer(
        (host, port),
        mcp_server=mcp_server,
        token_service=token_service,
        auth_required=auth_required,
    )
    return httpd
