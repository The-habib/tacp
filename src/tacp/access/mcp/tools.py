"""MCP Tool Registry and Dispatcher for TACP."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from tacp.control.identity import Principal, RequestContext
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.capability_service import CapabilityService
from tacp.core.filesystem_service import FilesystemService
from tacp.core.process_service import ProcessService
from tacp.core.system_service import SystemService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.audit import AuditEvent
from tacp.domain.errors import (
    ErrorCode,
    TacpNotFoundError,
    TacpSecurityError,
    TacpValidationError,
)
from tacp.infrastructure.logging import redact_dict


class McpToolRegistry:
    """Registers and executes TACP tools conforming to the MCP specification."""

    def __init__(
        self,
        capability_service: CapabilityService,
        policy_engine: PolicyEngine,
        audit_service: AuditService,
        workspace_service: WorkspaceService,
        filesystem_service: FilesystemService,
        process_service: ProcessService,
        system_service: SystemService,
    ) -> None:
        self.capability_service = capability_service
        self.policy_engine = policy_engine
        self.audit_service = audit_service
        self.workspace_service = workspace_service
        self.filesystem_service = filesystem_service
        self.process_service = process_service
        self.system_service = system_service

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return tool definitions formatted for MCP tools/list."""
        tools = []
        for cap in self.capability_service.list_raw():
            schema = cap.input_schema if cap.input_schema else {"type": "object", "properties": {}}
            tools.append(
                {
                    "name": cap.name,
                    "description": cap.description,
                    "inputSchema": schema,
                }
            )
        return tools

    def normalize_tool_name(self, name: str) -> str:
        """Allow both dot-notation (fs.read) and underscore-notation (fs_read)."""
        valid_names = {c.name for c in self.capability_service.list_raw()}
        if name in valid_names:
            return name
        dot_name = name.replace("_", ".", 1)
        if dot_name in valid_names:
            return dot_name
        return name

    def execute_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        principal: Optional[Principal] = None,
    ) -> Dict[str, Any]:
        """Execute a tool with policy enforcement and audit logging."""
        args = arguments or {}
        normalized_name = self.normalize_tool_name(name)

        # 1. Resolve capability
        cap = self.capability_service.get_capability(normalized_name)

        # 2. Build Principal and Context
        client_principal = principal or Principal(
            id="mcp-client",
            role="agent",
        )
        context = RequestContext(
            capability=cap.name,
            principal=client_principal,
        )

        # 3. Workspace resolution if specified
        ws = None
        workspace_id = args.get("workspace_id")
        if workspace_id:
            ws = self.workspace_service.get_workspace(workspace_id)

        # 4. Policy evaluation
        start_time = time.monotonic()
        decision = self.policy_engine.evaluate_request(context, workspace=ws)
        duration_ms = int((time.monotonic() - start_time) * 1000)

        if not decision.allowed:
            self.audit_service.record_event(
                AuditEvent(
                    capability=cap.name,
                    action=cap.name,
                    policy_decision="DENIED",
                    result="FAILED",
                    duration_ms=duration_ms,
                    principal=client_principal.id,
                    request_id=context.request_id,
                    workspace_id=workspace_id,
                    parameters_redacted=redact_dict(args),
                )
            )
            raise TacpSecurityError(
                ErrorCode.NOT_AUTHORIZED,
                f"Access denied: {decision.reason}",
            )

        # 5. Dispatch to core service
        try:
            result = self._dispatch(cap.name, args)
            duration_ms = int((time.monotonic() - start_time) * 1000)
            self.audit_service.record_event(
                AuditEvent(
                    capability=cap.name,
                    action=cap.name,
                    policy_decision="ALLOWED",
                    result="SUCCESS",
                    duration_ms=duration_ms,
                    principal=client_principal.id,
                    request_id=context.request_id,
                    workspace_id=workspace_id,
                    parameters_redacted=redact_dict(args),
                )
            )
            return result
        except Exception as exc:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            self.audit_service.record_event(
                AuditEvent(
                    capability=cap.name,
                    action=cap.name,
                    policy_decision="ALLOWED",
                    result=f"ERROR: {exc}",
                    duration_ms=duration_ms,
                    principal=client_principal.id,
                    request_id=context.request_id,
                    workspace_id=workspace_id,
                    parameters_redacted=redact_dict(args),
                )
            )
            raise

    def _dispatch(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Route tool execution to the appropriate service."""
        if name == "system.inspect":
            return self.system_service.inspect_system()
        elif name == "system.health":
            return self.system_service.get_health()
        elif name == "system.version":
            return self.system_service.get_version()
        elif name == "capabilities.list":
            return {"capabilities": self.capability_service.list_capabilities()}
        elif name == "workspace.list":
            return {"workspaces": self.workspace_service.list_workspaces()}
        elif name == "workspace.inspect":
            ws_id = args.get("workspace_id")
            if not ws_id:
                raise TacpValidationError("Missing required parameter: workspace_id")
            return self.workspace_service.inspect_workspace(ws_id)
        elif name == "fs.list":
            ws_id = args.get("workspace_id")
            if not ws_id:
                raise TacpValidationError("Missing required parameter: workspace_id")
            return self.filesystem_service.list_dir(
                workspace_id=ws_id,
                subpath=args.get("subpath", ""),
            )
        elif name == "fs.stat":
            ws_id = args.get("workspace_id")
            subpath = args.get("subpath")
            if not ws_id or subpath is None:
                raise TacpValidationError("Missing required parameters: workspace_id and subpath")
            return self.filesystem_service.stat_path(
                workspace_id=ws_id,
                subpath=subpath,
            )
        elif name == "fs.read":
            ws_id = args.get("workspace_id")
            subpath = args.get("subpath")
            if not ws_id or subpath is None:
                raise TacpValidationError("Missing required parameters: workspace_id and subpath")
            return self.filesystem_service.read_file(
                workspace_id=ws_id,
                subpath=subpath,
            )
        elif name == "fs.search":
            ws_id = args.get("workspace_id")
            query = args.get("query")
            if not ws_id or not query:
                raise TacpValidationError("Missing required parameters: workspace_id and query")
            return self.filesystem_service.search_files(
                workspace_id=ws_id,
                query=query,
                subpath=args.get("subpath", ""),
            )
        elif name == "process.list":
            return self.process_service.list_processes()
        elif name == "process.inspect":
            pid = args.get("pid")
            if pid is None:
                raise TacpValidationError("Missing required parameter: pid")
            return self.process_service.inspect_process(pid=int(pid))
        elif name == "audit.recent":
            limit = args.get("limit", 20)
            events = self.audit_service.get_recent_events(limit=int(limit))
            return {"events": events}
        else:
            raise TacpNotFoundError(f"Unhandled tool: {name}")
