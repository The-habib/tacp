"""MCP Tool Registry and Dispatcher for TACP."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional, Set

from tacp.control.identity import Principal, RequestContext
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.capability_service import _CAPABILITIES_BY_NAME, CapabilityService
from tacp.core.execution_service import ExecutionService
from tacp.core.filesystem_service import FilesystemService
from tacp.core.patch_service import PatchService
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
        patch_service: Optional[PatchService] = None,
        execution_service: Optional[ExecutionService] = None,
        lease_engine: Optional[Any] = None,
        device_registry: Optional[Any] = None,
    ) -> None:
        self.capability_service = capability_service
        self.policy_engine = policy_engine
        self.audit_service = audit_service
        self.workspace_service = workspace_service
        self.filesystem_service = filesystem_service
        self.process_service = process_service
        self.system_service = system_service
        self.patch_service = patch_service
        self.execution_service = execution_service
        self.lease_engine = lease_engine
        self.device_registry = device_registry
        self._default_principal = Principal.local_agent(agent_id="mcp-client")
        self._cached_tools_list: Optional[List[Dict[str, Any]]] = None
        self._valid_names_cache: Optional[Set[str]] = None
        self._normalized_cache: Dict[str, str] = {}

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return tool definitions formatted for MCP tools/list."""
        if self._cached_tools_list is not None:
            return self._cached_tools_list

        tools = []
        profile = getattr(self.policy_engine, "trust_profile", "BALANCED")
        if profile in ("LOCKDOWN", "REMOTE_READ_ONLY"):
            include_mutating = False
            include_batch = False
            include_execution = False
        else:
            include_mutating = bool(
                self.patch_service and self.patch_service.config.mutation_enabled
            )
            include_batch = bool(
                include_mutating
                and self.patch_service
                and self.patch_service.config.batch_mutation_enabled
            )
            include_execution = bool(
                self.execution_service and self.execution_service.config.execution_enabled
            )
        for cap in self.capability_service.list_raw(
            include_mutating=include_mutating,
            include_batch=include_batch,
            include_execution=include_execution,
        ):
            schema = cap.input_schema if cap.input_schema else {"type": "object", "properties": {}}
            tools.append(
                {
                    "name": cap.name,
                    "description": cap.description,
                    "inputSchema": schema,
                }
            )

        if self.device_registry:
            existing_names = {t["name"] for t in tools}
            for dev_tool in self.device_registry.get_mcp_tools():
                if dev_tool["name"] not in existing_names:
                    tools.append(dev_tool)

        self._cached_tools_list = tools
        return tools

    def normalize_tool_name(self, name: str) -> str:
        """Allow dot-notation, underscore-notation, and tacp_ prefix with O(1) lookup."""
        if name in self._normalized_cache:
            return self._normalized_cache[name]

        if self._valid_names_cache is None:
            include_mutating = bool(
                self.patch_service and self.patch_service.config.mutation_enabled
            )
            include_batch = bool(
                include_mutating
                and self.patch_service
                and self.patch_service.config.batch_mutation_enabled
            )
            include_execution = bool(
                self.execution_service and self.execution_service.config.execution_enabled
            )
            valid = {
                c.name
                for c in self.capability_service.list_raw(
                    include_mutating=include_mutating,
                    include_batch=include_batch,
                    include_execution=include_execution,
                )
            }
            if self.device_registry:
                valid.update(self.device_registry._capabilities.keys())
            self._valid_names_cache = valid

        valid_names = self._valid_names_cache
        res = name
        if name in valid_names:
            res = name
        else:
            clean_name = name[5:] if name.startswith("tacp_") else name
            if clean_name in valid_names:
                res = clean_name
            else:
                dot_name = clean_name.replace("_", ".", 1)
                if dot_name in valid_names:
                    res = dot_name

        self._normalized_cache[name] = res
        return res

    def execute_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        principal: Optional[Principal] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a tool with policy enforcement and audit logging."""
        args = arguments or {}
        normalized_name = self.normalize_tool_name(name)

        # 1. Resolve capability (O(1))
        cap_name = normalized_name
        cap = _CAPABILITIES_BY_NAME.get(normalized_name)
        if cap is not None:
            cap_name = cap.name
        elif self.device_registry and self.device_registry.get(normalized_name):
            cap = None
        else:
            raise TacpNotFoundError(f"Capability not found: {normalized_name}")

        # 2. Build Principal and Context
        client_principal = principal or self._default_principal
        context = RequestContext(
            capability=cap_name,
            principal=client_principal,
            request_id=request_id or uuid.uuid4().hex,
        )

        from tacp.core.admission import get_admission_controller

        with get_admission_controller().acquire(cap_name):
            # 3. For mutating and execution capabilities, dispatch directly
            # to services (unified pipeline)
            lease_id = args.get("lease_id")
            if normalized_name in ("workspace.patch", "workspace.patch_batch", "execution.request"):
                return self._dispatch(
                    cap_name,
                    args,
                    principal=client_principal,
                    request_id=context.request_id,
                    lease_id=lease_id,
                )

            # 4. Workspace resolution for read-only capabilities if specified
            ws = None
            workspace_id = args.get("workspace_id")
            if workspace_id:
                ws = self.workspace_service.get_workspace(workspace_id)

            start_time = time.monotonic()
            decision = self.policy_engine.evaluate_request(
                context,
                workspace=ws,
            )
            duration_ms = int((time.monotonic() - start_time) * 1000)

            if not decision.allowed:
                self.audit_service.record_event(
                    AuditEvent(
                        capability=cap_name,
                        action=cap_name,
                        policy_decision=decision.decision_type,
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

            # 5. Dispatch to read-only service
            try:
                result = self._dispatch(
                    cap_name,
                    args,
                    principal=client_principal,
                    request_id=context.request_id,
                )
                duration_ms = int((time.monotonic() - start_time) * 1000)
                self.audit_service.record_event(
                    AuditEvent(
                        capability=cap_name,
                        action=cap_name,
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
                        capability=cap_name,
                        action=cap_name,
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

    def _dispatch(
        self,
        name: str,
        args: Dict[str, Any],
        principal: Optional[Principal] = None,
        request_id: Optional[str] = None,
        lease_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Route tool execution to the appropriate service."""
        if name == "system.inspect":
            return self.system_service.inspect_system()
        elif name == "system.health":
            return self.system_service.get_health()
        elif name == "system.version":
            return self.system_service.get_version()
        elif name == "capabilities.list":
            include_mutating = bool(
                self.patch_service and self.patch_service.config.mutation_enabled
            )
            include_batch = bool(
                include_mutating
                and self.patch_service
                and self.patch_service.config.batch_mutation_enabled
            )
            return {
                "capabilities": self.capability_service.list_capabilities(
                    include_mutating=include_mutating,
                    include_batch=include_batch,
                )
            }
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
            subpath = str(
                args.get("subpath") if args.get("subpath") is not None else args.get("path", "")
            )
            return self.filesystem_service.list_dir(
                workspace_id=ws_id,
                subpath=subpath,
            )
        elif name == "fs.stat":
            ws_id = args.get("workspace_id")
            subpath = args.get("subpath") if args.get("subpath") is not None else args.get("path")
            if not ws_id or subpath is None:
                raise TacpValidationError(
                    "Missing required parameters: workspace_id and subpath (or path)"
                )
            return self.filesystem_service.stat_path(
                workspace_id=ws_id,
                subpath=subpath,
            )
        elif name == "fs.read":
            ws_id = args.get("workspace_id")
            subpath = args.get("subpath") if args.get("subpath") is not None else args.get("path")
            if not ws_id or subpath is None:
                raise TacpValidationError(
                    "Missing required parameters: workspace_id and subpath (or path)"
                )
            return self.filesystem_service.read_file(
                workspace_id=ws_id,
                subpath=subpath,
            )
        elif name == "fs.search":
            ws_id = args.get("workspace_id")
            query = args.get("query")
            if not ws_id or not query:
                raise TacpValidationError("Missing required parameters: workspace_id and query")
            subpath = str(
                args.get("subpath") if args.get("subpath") is not None else args.get("path", "")
            )
            return self.filesystem_service.search_files(
                workspace_id=ws_id,
                query=query,
                subpath=subpath,
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
        elif name == "audit.verify_integrity":
            is_valid = self.audit_service.verify_integrity()
            return {"valid": is_valid}
        elif name == "workspace.patch":
            if not self.patch_service:
                raise TacpSecurityError(
                    ErrorCode.POLICY_DENIED,
                    "Patch service is not configured or disabled",
                )
            ws_id = args.get("workspace_id")
            subpath = args.get("subpath")
            patch_content = args.get("patch_content")
            base_checksum = args.get("base_checksum")
            if not ws_id or not subpath or not patch_content or not base_checksum:
                raise TacpValidationError(
                    "Missing required parameters for workspace.patch: "
                    "workspace_id, subpath, patch_content, base_checksum"
                )
            patch_res = self.patch_service.execute_patch(
                workspace_id=ws_id,
                subpath=subpath,
                patch_content=patch_content,
                base_checksum=base_checksum,
                dry_run=bool(args.get("dry_run", False)),
                approval_token=args.get("approval_token"),
                principal_id=(principal.id if principal else "mcp-client"),
                request_id=request_id,
                principal=principal,
                lease_id=lease_id,
            )
            return patch_res.to_dict()
        elif name == "workspace.patch_batch":
            if not self.patch_service:
                raise TacpSecurityError(
                    ErrorCode.POLICY_DENIED,
                    "Patch service is not configured or disabled",
                )
            ws_id = args.get("workspace_id")
            patches = args.get("patches")
            if not ws_id or not patches:
                raise TacpValidationError(
                    "Missing required parameters for workspace.patch_batch: workspace_id, patches"
                )
            if not isinstance(patches, list):
                raise TacpValidationError("Parameter 'patches' must be a list")
            batch_res = self.patch_service.execute_patch_batch(
                workspace_id=ws_id,
                patches=patches,
                dry_run=bool(args.get("dry_run", False)),
                approval_token=args.get("approval_token"),
                principal_id=(principal.id if principal else "mcp-client"),
                request_id=request_id,
                principal=principal,
                lease_id=lease_id,
            )
            return batch_res.to_dict()
        elif name == "execution.request":
            if not self.execution_service or not self.execution_service.config.execution_enabled:
                raise TacpSecurityError(
                    ErrorCode.POLICY_DENIED,
                    "Execution service is not configured or disabled",
                )
            ws_id = args.get("workspace_id")
            executable = args.get("executable")
            argv = args.get("argv")
            if not ws_id or not executable or argv is None:
                raise TacpValidationError(
                    "Missing required parameters for execution.request: "
                    "workspace_id, executable, argv"
                )
            if not isinstance(argv, list):
                raise TacpValidationError("Parameter 'argv' must be a list of strings")

            exec_res = self.execution_service.execute_command(
                workspace_id=ws_id,
                executable=executable,
                argv=argv,
                cwd=args.get("cwd"),
                environment=args.get("environment"),
                timeout_seconds=args.get("timeout_seconds"),
                dry_run=bool(args.get("dry_run", False)),
                approval_token=args.get("approval_token"),
                principal_id=(principal.id if principal else "mcp-client"),
                request_id=request_id,
                principal=principal,
                lease_id=lease_id,
            )
            return exec_res.to_dict()

        elif self.device_registry and self.device_registry.get(name):
            res = self.device_registry.dispatch(name, args)
            return dict(res) if isinstance(res, dict) else {"result": res}

        else:
            raise TacpNotFoundError(f"Unhandled tool: {name}")
