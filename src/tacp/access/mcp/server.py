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
                        "resources": {},
                        "prompts": {},
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
                        "resources": {},
                        "prompts": {},
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
            params = request.params or {}
            category = params.get("category")
            cursor = params.get("cursor")
            limit = params.get("limit")

            tools = self.tool_registry.list_tools()
            if category:
                cat_lower = str(category).lower()
                tools = [
                    t for t in tools
                    if cat_lower in t.get("name", "").lower() or cat_lower in t.get("description", "").lower()
                ]

            total_tools = len(tools)
            start_idx = 0
            if cursor:
                try:
                    start_idx = int(cursor)
                except ValueError:
                    start_idx = 0

            next_cursor = None
            if limit and isinstance(limit, int) and limit > 0:
                end_idx = start_idx + limit
                page_tools = tools[start_idx:end_idx]
                if end_idx < total_tools:
                    next_cursor = str(end_idx)
            else:
                page_tools = tools[start_idx:]

            res_dict = {
                "tools": page_tools,
                "cacheScope": "public",
                "ttlMs": 60000,
                "resultType": "complete",
            }
            if next_cursor:
                res_dict["nextCursor"] = next_cursor
            return McpResponse(id=req_id, result=res_dict)

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

        elif method == "resources/list":
            resources = [
                {
                    "uri": "tacp://device/info",
                    "name": "Device System Info",
                    "description": "Android device hardware, model, manufacturer, Android release, SDK, and architecture",
                    "mimeType": "application/json",
                },
                {
                    "uri": "tacp://device/battery",
                    "name": "Battery Status",
                    "description": "Live battery percentage, charging state, temperature, and health",
                    "mimeType": "application/json",
                },
                {
                    "uri": "tacp://device/properties",
                    "name": "Android System Properties",
                    "description": "Android getprop system properties and build fingerprint",
                    "mimeType": "application/json",
                },
                {
                    "uri": "tacp://device/snapshot",
                    "name": "Full Device Health Snapshot",
                    "description": "Consolidated snapshot of battery, memory, storage, uptime, and load",
                    "mimeType": "application/json",
                },
                {
                    "uri": "tacp://storage/overview",
                    "name": "Storage Space Overview",
                    "description": "Storage overview across internal, termux-home, and shared-storage mounts",
                    "mimeType": "application/json",
                },
                {
                    "uri": "tacp://network/interfaces",
                    "name": "Network Interfaces",
                    "description": "Active network interfaces, IP addresses, MTU, and status",
                    "mimeType": "application/json",
                },
                {
                    "uri": "tacp://system/health",
                    "name": "TACP System Health",
                    "description": "Health status of database, storage, and control plane",
                    "mimeType": "application/json",
                },
                {
                    "uri": "tacp://capabilities/list",
                    "name": "Device Capabilities Matrix",
                    "description": "All registered device capabilities, required privileges, and active backends",
                    "mimeType": "application/json",
                },
            ]
            return McpResponse(
                id=req_id,
                result={
                    "resources": resources,
                    "cacheScope": "public",
                    "ttlMs": 30000,
                    "resultType": "complete",
                },
            )

        elif method == "resources/read":
            uri = request.params.get("uri")
            if not uri or not isinstance(uri, str):
                return McpResponse(
                    id=req_id,
                    error={"code": INVALID_PARAMS, "message": "Missing 'uri' in resources/read"},
                )

            data: Any = None
            try:
                if uri == "tacp://device/info":
                    data = self.tool_registry.execute_tool("device.info", {})
                elif uri == "tacp://device/battery":
                    data = self.tool_registry.execute_tool("device.battery", {})
                elif uri == "tacp://device/properties":
                    data = self.tool_registry.execute_tool("device.properties", {})
                elif uri == "tacp://device/snapshot":
                    data = self.tool_registry.execute_tool("device.snapshot", {})
                elif uri == "tacp://storage/overview":
                    data = self.tool_registry.execute_tool("storage.overview", {})
                elif uri == "tacp://network/interfaces":
                    data = self.tool_registry.execute_tool("network.interfaces", {})
                elif uri == "tacp://system/health":
                    data = self.tool_registry.system_service.get_health()
                elif uri == "tacp://capabilities/list":
                    if self.tool_registry.device_registry:
                        data = {"capabilities": self.tool_registry.device_registry.list_capabilities()}
                    else:
                        data = {"capabilities": self.tool_registry.capability_service.list_capabilities()}
                else:
                    return McpResponse(
                        id=req_id,
                        error={"code": INVALID_PARAMS, "message": f"Resource not found: {uri}"},
                    )

                return McpResponse(
                    id=req_id,
                    result={
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "application/json",
                                "text": json.dumps(data, indent=2),
                            }
                        ]
                    },
                )
            except Exception as exc:
                return McpResponse(
                    id=req_id,
                    error={"code": INTERNAL_ERROR, "message": f"Failed to read resource '{uri}': {exc}"},
                )

        elif method == "prompts/list":
            prompts = [
                {
                    "name": "device-diagnostics",
                    "description": "Run comprehensive diagnostic check across all Android subsystems and backends",
                    "arguments": [],
                },
                {
                    "name": "inspect-device",
                    "description": "Inspect device hardware, battery, storage, and running processes",
                    "arguments": [],
                },
                {
                    "name": "troubleshoot-network",
                    "description": "Diagnose network interfaces, DNS resolution, and internet connectivity",
                    "arguments": [],
                },
            ]
            return McpResponse(
                id=req_id,
                result={"prompts": prompts},
            )

        elif method == "prompts/get":
            prompt_name = request.params.get("name")
            if not prompt_name:
                return McpResponse(
                    id=req_id,
                    error={"code": INVALID_PARAMS, "message": "Missing 'name' in prompts/get"},
                )

            if prompt_name == "device-diagnostics":
                return McpResponse(
                    id=req_id,
                    result={
                        "description": "Comprehensive diagnostic check for Android device",
                        "messages": [
                            {
                                "role": "user",
                                "content": {
                                    "type": "text",
                                    "text": (
                                        "Please run comprehensive diagnostic checks on this Android device using "
                                        "TACP device tools (device.snapshot, storage.overview, network.diagnostics, "
                                        "and diagnostics.bundle) and report hardware state, backend availability, "
                                        "and any degraded components."
                                    ),
                                },
                            }
                        ],
                    },
                )
            elif prompt_name == "inspect-device":
                return McpResponse(
                    id=req_id,
                    result={
                        "description": "Inspect device hardware, battery, and storage",
                        "messages": [
                            {
                                "role": "user",
                                "content": {
                                    "type": "text",
                                    "text": (
                                        "Please inspect this Android device using device.info, device.battery, "
                                        "and storage.overview to provide a complete device health overview."
                                    ),
                                },
                            }
                        ],
                    },
                )
            elif prompt_name == "troubleshoot-network":
                return McpResponse(
                    id=req_id,
                    result={
                        "description": "Diagnose network interfaces and connectivity",
                        "messages": [
                            {
                                "role": "user",
                                "content": {
                                    "type": "text",
                                    "text": (
                                        "Please diagnose network connectivity on this device using "
                                        "network.interfaces, wifi.status, and network.ping."
                                    ),
                                },
                            }
                        ],
                    },
                )
            else:
                return McpResponse(
                    id=req_id,
                    error={"code": INVALID_PARAMS, "message": f"Prompt not found: {prompt_name}"},
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


def create_mcp_server(
    config: TacpConfig | None = None,
    enable_device_capabilities: bool | None = None,
) -> McpServer:
    """Factory creating a fully wired McpServer instance."""
    cfg = config or TacpConfig.load()
    db = Database(cfg.db_path)
    db.connect()

    audit_service = AuditService(db)
    lease_engine = LeaseEngine(db)

    device_registry = None
    should_enable_device = (
        enable_device_capabilities
        if enable_device_capabilities is not None
        else getattr(cfg, "device_control_enabled", False)
    )
    if should_enable_device:
        from tacp.engine.registry import default_registry

        device_registry = default_registry

    policy_engine = PolicyEngine(
        read_only_enforced=cfg.read_only,
        mutation_enabled=cfg.mutation_enabled,
        batch_mutation_enabled=cfg.batch_mutation_enabled,
        execution_enabled=cfg.execution_enabled,
        network_enabled=cfg.network_enabled,
        trust_profile=cfg.trust_profile,
        lease_engine=lease_engine,
        remote_enabled=cfg.remote_enabled,
        remote_read_only=cfg.remote_read_only,
        remote_mutation_enabled=cfg.remote_mutation_enabled,
        remote_execution_enabled=cfg.remote_execution_enabled,
        device_control_enabled=should_enable_device,
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
        device_registry=device_registry,
    )

    return McpServer(tool_registry=tool_registry, config=cfg)
