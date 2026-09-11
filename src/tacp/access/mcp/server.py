"""Stdio MCP server loop for TACP."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import TextIO

from tacp.access.mcp.protocol import (
    DEFAULT_PROTOCOL_VERSION,
    INTERNAL_ERROR,
    INVALID_PARAMS,
    KNOWN_PROTOCOL_VERSIONS,
    LEGACY_PROTOCOL_VERSION,
    METHOD_NOT_FOUND,
    McpProtocolError,
    McpRequest,
    McpResponse,
    parse_message,
)
from tacp.access.mcp.tools import McpToolRegistry
from tacp.control.approval import ApprovalEngine
from tacp.control.lease import LeaseEngine
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.capability_service import CapabilityService
from tacp.core.execution_service import ExecutionService
from tacp.core.filesystem_service import FilesystemService
from tacp.core.lock_service import LockService
from tacp.core.patch_service import PatchService
from tacp.core.process_service import ProcessService
from tacp.core.system_service import SystemService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import TacpError
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database
from tacp.infrastructure.logging import redact_secrets
from tacp.providers.filesystem import FilesystemProvider
from tacp.providers.process import ProcessProvider

logger = logging.getLogger(__name__)

# Backward compatibility alias
MCP_PROTOCOL_VERSION = LEGACY_PROTOCOL_VERSION


class McpServer:
    """Synchronous stdio Model Context Protocol (MCP) server.

    Supports modern (2026-07-28) and legacy (2024-11-05) protocol revisions.
    """

    def __init__(self, tool_registry: McpToolRegistry, config: TacpConfig) -> None:
        self.tool_registry = tool_registry
        self.config = config

    def handle_request(self, request: McpRequest) -> McpResponse | None:
        """Process a single JSON-RPC request and return the response."""
        if request.is_notification:
            return None

        method = request.method
        req_id = request.id

        if method == "server/discover":
            # MCP 2026-07-28 stateless server discovery
            return McpResponse(
                id=req_id,
                result={
                    "supportedVersions": list(KNOWN_PROTOCOL_VERSIONS),
                    "capabilities": {
                        "tools": {},
                    },
                    "cacheScope": "public",
                    "ttlMs": 60000,
                    "resultType": "complete",
                    "instructions": (
                        "TACP (Termux AI Control Plane) is a governed MCP server "
                        "providing safe inspection and policy-controlled workspace operations "
                        "for Termux workspaces, processes, system status, and audit logs."
                    ),
                },
            )

        elif method == "initialize":
            # MCP 2024-11-05 through 2025-11-25 handshake negotiation
            client_version = request.params.get("protocolVersion")
            if client_version in KNOWN_PROTOCOL_VERSIONS:
                negotiated_version = client_version
            elif client_version:
                negotiated_version = DEFAULT_PROTOCOL_VERSION
            else:
                negotiated_version = LEGACY_PROTOCOL_VERSION

            return McpResponse(
                id=req_id,
                result={
                    "protocolVersion": negotiated_version,
                    "capabilities": {
                        "tools": {},
                    },
                    "serverInfo": {
                        "name": "tacp",
                        "version": self.config.version,
                    },
                    "instructions": (
                        "TACP (Termux AI Control Plane) is a governed MCP server "
                        "providing safe inspection and policy-controlled workspace operations."
                    ),
                },
            )

        elif method == "ping":
            return McpResponse(id=req_id, result={})

        elif method == "tools/list":
            tools = self.tool_registry.list_tools()
            return McpResponse(
                id=req_id,
                result={
                    "tools": tools,
                    "cacheScope": "public",
                    "ttlMs": 60000,
                    "resultType": "complete",
                },
            )

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

            # Handle per-request _meta parameter (MCP 2026-07-28 progress tokens, correlation IDs)
            _meta = request.params.get("_meta")
            if _meta is not None and not isinstance(_meta, dict):
                return McpResponse(
                    id=req_id,
                    error={"code": INVALID_PARAMS, "message": "'_meta' must be an object"},
                )

            request_id = None
            if _meta:
                request_id = str(_meta.get("requestId") or _meta.get("progressToken") or "")
            if not request_id:
                request_id = str(req_id)

            try:
                result = self.tool_registry.execute_tool(
                    tool_name, arguments, request_id=request_id
                )
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
                        "resultType": "complete",
                    },
                )
            except TacpError as exc:
                safe_msg = redact_secrets(exc.message)
                if exc.details:
                    err_dict = {
                        "error": exc.__class__.__name__,
                        "code": exc.code.value,
                        "message": safe_msg,
                        **exc.details,
                    }
                    err_text = json.dumps(err_dict, indent=2)
                else:
                    err_text = f"Error ({exc.code.value}): {safe_msg}"
                return McpResponse(
                    id=req_id,
                    result={
                        "content": [
                            {
                                "type": "text",
                                "text": err_text,
                            }
                        ],
                        "isError": True,
                        "resultType": "complete",
                    },
                )
            except Exception:
                logger.exception(
                    "Internal error in tools/call for %s (req_id=%s)", tool_name, req_id
                )
                err_text = (
                    "Internal Error: An unexpected internal error occurred "
                    f"(Request ID: {request_id})"
                )
                return McpResponse(
                    id=req_id,
                    result={
                        "content": [
                            {
                                "type": "text",
                                "text": err_text,
                            }
                        ],
                        "isError": True,
                        "resultType": "complete",
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
    lease_engine = LeaseEngine(db)
    policy_engine = PolicyEngine(
        read_only_enforced=cfg.read_only,
        mutation_enabled=cfg.mutation_enabled,
        batch_mutation_enabled=cfg.batch_mutation_enabled,
        execution_enabled=cfg.execution_enabled,
        network_enabled=cfg.network_enabled,
        trust_profile=cfg.trust_profile,
        lease_engine=lease_engine,
    )
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
    lock_service = LockService(db)
    approval_engine = ApprovalEngine(db)

    patch_service = PatchService(
        db=db,
        workspace_service=workspace_service,
        policy_engine=policy_engine,
        fs_provider=fs_provider,
        audit_service=audit_service,
        lock_service=lock_service,
        approval_engine=approval_engine,
        config=cfg,
        lease_engine=lease_engine,
    )

    exec_service = ExecutionService(
        db=db,
        config=cfg,
        policy_engine=policy_engine,
        approval_engine=approval_engine,
        audit_service=audit_service,
        workspace_service=workspace_service,
        lease_engine=lease_engine,
    )

    tool_registry = McpToolRegistry(
        capability_service=capability_service,
        policy_engine=policy_engine,
        audit_service=audit_service,
        workspace_service=workspace_service,
        filesystem_service=filesystem_service,
        process_service=process_service,
        system_service=system_service,
        patch_service=patch_service,
        execution_service=exec_service,
        lease_engine=lease_engine,
    )

    return McpServer(tool_registry=tool_registry, config=cfg)
