"""Stdio MCP server loop for TACP."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO

from tacp.access.mcp.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    McpProtocolError,
    McpRequest,
    McpResponse,
    parse_message,
)
from tacp.access.mcp.tools import McpToolRegistry
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.capability_service import CapabilityService
from tacp.core.filesystem_service import FilesystemService
from tacp.core.process_service import ProcessService
from tacp.core.system_service import SystemService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import TacpError
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database
from tacp.providers.filesystem import FilesystemProvider
from tacp.providers.process import ProcessProvider

MCP_PROTOCOL_VERSION = "2024-11-05"


class McpServer:
    """Synchronous stdio Model Context Protocol (MCP) server."""

    def __init__(self, tool_registry: McpToolRegistry, config: TacpConfig) -> None:
        self.tool_registry = tool_registry
        self.config = config

    def handle_request(self, request: McpRequest) -> McpResponse | None:
        """Process a single JSON-RPC request and return the response."""
        if request.is_notification:
            return None

        method = request.method
        req_id = request.id

        if method == "initialize":
            return McpResponse(
                id=req_id,
                result={
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {},
                    },
                    "serverInfo": {
                        "name": "tacp",
                        "version": self.config.version,
                    },
                },
            )

        elif method == "ping":
            return McpResponse(id=req_id, result={})

        elif method == "tools/list":
            tools = self.tool_registry.list_tools()
            return McpResponse(id=req_id, result={"tools": tools})

        elif method == "tools/call":
            tool_name = request.params.get("name")
            if not tool_name or not isinstance(tool_name, str):
                return McpResponse(
                    id=req_id,
                    error={"code": INVALID_PARAMS, "message": "Missing 'name' in tools/call"},
                )

            arguments = request.params.get("arguments", {})
            if not isinstance(arguments, dict):
                return McpResponse(
                    id=req_id,
                    error={"code": INVALID_PARAMS, "message": "'arguments' must be an object"},
                )

            try:
                result = self.tool_registry.execute_tool(tool_name, arguments)
                return McpResponse(
                    id=req_id,
                    result={
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, indent=2),
                            }
                        ],
                        "isError": False,
                    },
                )
            except TacpError as exc:
                return McpResponse(
                    id=req_id,
                    result={
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error ({exc.code.value}): {exc.message}",
                            }
                        ],
                        "isError": True,
                    },
                )
            except Exception as exc:
                return McpResponse(
                    id=req_id,
                    result={
                        "content": [
                            {
                                "type": "text",
                                "text": f"Internal Error: {exc}",
                            }
                        ],
                        "isError": True,
                    },
                )

        else:
            return McpResponse(
                id=req_id,
                error={
                    "code": METHOD_NOT_FOUND,
                    "message": f"Method not found: {method}",
                },
            )

    def run_stdio(self, reader: TextIO | None = None, writer: TextIO | None = None) -> None:
        """Run the stdio message loop until EOF."""
        in_stream = reader or sys.stdin
        out_stream = writer or sys.stdout

        for line in in_stream:
            stripped = line.strip()
            if not stripped:
                continue

            try:
                request = parse_message(stripped)
                response = self.handle_request(request)
                if response is not None:
                    out_stream.write(response.to_json() + "\n")
                    out_stream.flush()
            except McpProtocolError as exc:
                err_resp = McpResponse(id=None, error=exc.to_dict())
                out_stream.write(err_resp.to_json() + "\n")
                out_stream.flush()
            except Exception as exc:
                err_resp = McpResponse(
                    id=None,
                    error={"code": INTERNAL_ERROR, "message": f"Fatal server error: {exc}"},
                )
                out_stream.write(err_resp.to_json() + "\n")
                out_stream.flush()


def create_mcp_server(config: TacpConfig | None = None) -> McpServer:
    """Factory creating a fully wired McpServer instance."""
    cfg = config or TacpConfig.load()
    db = Database(cfg.db_path)
    db.connect()

    audit_service = AuditService(db)
    policy_engine = PolicyEngine(read_only_enforced=cfg.read_only)
    workspace_service = WorkspaceService(db)

    # Ensure a default workspace exists
    if not workspace_service.list_workspaces():
        projects_dir = Path.home() / "projects"
        root_to_register = projects_dir if projects_dir.exists() else Path.cwd()
        workspace_service.register_workspace(name="default", root_path=root_to_register)

    fs_provider = FilesystemProvider(limits=cfg.limits)
    filesystem_service = FilesystemService(workspace_service, fs_provider)

    proc_provider = ProcessProvider(limits=cfg.limits)
    process_service = ProcessService(proc_provider)

    system_service = SystemService(db)
    capability_service = CapabilityService()

    tool_registry = McpToolRegistry(
        capability_service=capability_service,
        policy_engine=policy_engine,
        audit_service=audit_service,
        workspace_service=workspace_service,
        filesystem_service=filesystem_service,
        process_service=process_service,
        system_service=system_service,
    )

    return McpServer(tool_registry=tool_registry, config=cfg)
