from typing import Any, Dict, List

from tacp.domain.capability import Capability

READONLY_CAPABILITIES: List[Capability] = [
    Capability(
        name="system.inspect",
        domain="system",
        description="Inspect host system, kernel, CPU architecture, memory, and Termux details",
        output_schema={"type": "object"},
    ),
    Capability(
        name="system.health",
        domain="system",
        description="Check TACP subsystem health, storage margins, and database connectivity",
        output_schema={"type": "object"},
    ),
    Capability(
        name="system.version",
        domain="system",
        description="Return TACP version and supported MCP protocol specification",
        output_schema={"type": "object"},
    ),
    Capability(
        name="capabilities.list",
        domain="capabilities",
        description="List all available TACP capabilities and their parameter schemas",
        output_schema={"type": "object"},
    ),
    Capability(
        name="workspace.list",
        domain="workspace",
        description="List all registered workspace roots and their status",
        output_schema={"type": "object"},
    ),
    Capability(
        name="workspace.inspect",
        domain="workspace",
        description="Inspect statistics, file counts, and git repository status of a workspace",
        input_schema={
            "type": "object",
            "properties": {"workspace_id": {"type": "string"}},
            "required": ["workspace_id"],
        },
        output_schema={"type": "object"},
    ),
    Capability(
        name="fs.list",
        domain="filesystem",
        description="List directory entries inside an authorized workspace root with metadata",
        input_schema={
            "type": "object",
            "properties": {"workspace_id": {"type": "string"}, "subpath": {"type": "string"}},
            "required": ["workspace_id"],
        },
        output_schema={"type": "object"},
    ),
    Capability(
        name="fs.stat",
        domain="filesystem",
        description=(
            "Get detailed metadata, permissions, and classification for a file or directory"
        ),
        input_schema={
            "type": "object",
            "properties": {"workspace_id": {"type": "string"}, "subpath": {"type": "string"}},
            "required": ["workspace_id", "subpath"],
        },
        output_schema={"type": "object"},
    ),
    Capability(
        name="fs.read",
        domain="filesystem",
        description="Safely read file content with output size truncation and secret protection",
        input_schema={
            "type": "object",
            "properties": {"workspace_id": {"type": "string"}, "subpath": {"type": "string"}},
            "required": ["workspace_id", "subpath"],
        },
        output_schema={"type": "object"},
    ),
    Capability(
        name="fs.search",
        domain="filesystem",
        description="Search file content within a workspace using substring or regex pattern",
        input_schema={
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string"},
                "query": {"type": "string"},
                "subpath": {"type": "string"},
            },
            "required": ["workspace_id", "query"],
        },
        output_schema={"type": "object"},
    ),
    Capability(
        name="process.list",
        domain="process",
        description="List running processes owned by the current Termux user",
        output_schema={"type": "object"},
    ),
    Capability(
        name="process.inspect",
        domain="process",
        description="Inspect command line, memory, and status of a specific user process PID",
        input_schema={
            "type": "object",
            "properties": {"pid": {"type": "integer"}},
            "required": ["pid"],
        },
        output_schema={"type": "object"},
    ),
    Capability(
        name="audit.recent",
        domain="audit",
        description="Retrieve recent tamper-evident audit events and authorization decisions",
        input_schema={"type": "object", "properties": {"limit": {"type": "integer"}}},
        output_schema={"type": "object"},
    ),
]

MUTATING_CAPABILITIES: List[Capability] = [
    Capability(
        name="workspace.patch",
        domain="workspace",
        description=(
            "Apply a governed unified diff patch to a text file within an authorized workspace"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "workspace_id": {
                    "type": "string",
                    "description": "Target workspace identifier",
                },
                "subpath": {
                    "type": "string",
                    "description": "Relative path to target file within workspace",
                },
                "patch_content": {
                    "type": "string",
                    "description": "Unified diff patch content",
                },
                "base_checksum": {
                    "type": "string",
                    "description": "Expected SHA-256 hex checksum of target file before patch",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Simulate patch application without modifying disk",
                },
                "approval_token": {
                    "type": "string",
                    "description": "Approval token if live mutation requires human sign-off",
                },
                "lease_id": {
                    "type": "string",
                    "description": (
                        "Optional capability lease identifier for pre-authorized mutation "
                        "under BALANCED profile"
                    ),
                },
            },
            "required": ["workspace_id", "subpath", "patch_content", "base_checksum"],
        },
        output_schema={"type": "object"},
    ),
    Capability(
        name="workspace.patch_batch",
        domain="workspace",
        description=(
            "Apply a governed atomic multi-file patch batch within an authorized workspace"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "workspace_id": {
                    "type": "string",
                    "description": "Target workspace identifier",
                },
                "patches": {
                    "type": "array",
                    "description": "List of patch items to apply atomically",
                    "items": {
                        "type": "object",
                        "properties": {
                            "subpath": {"type": "string"},
                            "patch_content": {"type": "string"},
                            "base_checksum": {"type": "string"},
                        },
                        "required": ["subpath", "patch_content", "base_checksum"],
                    },
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Simulate batch patch application without modifying disk",
                },
                "approval_token": {
                    "type": "string",
                    "description": "Approval token if live mutation requires human sign-off",
                },
                "lease_id": {
                    "type": "string",
                    "description": (
                        "Optional capability lease identifier for pre-authorized batch "
                        "mutation under BALANCED profile"
                    ),
                },
            },
            "required": ["workspace_id", "patches"],
        },
        output_schema={"type": "object"},
    ),
]

EXECUTION_CAPABILITIES: List[Capability] = [
    Capability(
        name="execution.request",
        domain="execution",
        description=(
            "Execute a governed, policy-controlled operating system command with "
            "strict arguments, workspace containment, and bounded output"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "workspace_id": {
                    "type": "string",
                    "description": "Target workspace identifier",
                },
                "executable": {
                    "type": "string",
                    "description": "Deterministic executable binary name (e.g. 'printf')",
                },
                "argv": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered array of string arguments passed to the executable",
                },
                "cwd": {
                    "type": "string",
                    "description": "Optional relative working directory within workspace",
                },
                "environment": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Optional safe environment variables",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 15, max: 60)",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Simulate policy checks without spawning a process",
                },
                "approval_token": {
                    "type": "string",
                    "description": "Approval token required for non-dry-run execution",
                },
                "lease_id": {
                    "type": "string",
                    "description": (
                        "Optional capability lease identifier for pre-authorized execution "
                        "under BALANCED profile"
                    ),
                },
            },
            "required": ["workspace_id", "executable", "argv"],
        },
        output_schema={"type": "object"},
    ),
]

ADMIN_CAPABILITIES: List[Capability] = [
    Capability(
        name="audit.verify_integrity",
        domain="audit",
        description=(
            "Verify the cryptographic hash chain and structural integrity of all audit records"
        ),
        output_schema={"type": "object"},
    ),
]


class CapabilityService:
    @staticmethod
    def list_capabilities(
        include_mutating: bool = False,
        include_batch: bool = False,
        include_execution: bool = False,
        include_admin: bool = False,
    ) -> List[Dict[str, Any]]:
        caps = list(READONLY_CAPABILITIES)
        if include_mutating:
            caps.append(MUTATING_CAPABILITIES[0])  # workspace.patch
            if include_batch:
                caps.append(MUTATING_CAPABILITIES[1])  # workspace.patch_batch
        if include_execution:
            caps.extend(EXECUTION_CAPABILITIES)
        if include_admin:
            caps.extend(ADMIN_CAPABILITIES)
        return [c.to_dict() for c in caps]

    @staticmethod
    def list_raw(
        include_mutating: bool = False,
        include_batch: bool = False,
        include_execution: bool = False,
        include_admin: bool = False,
    ) -> List[Capability]:
        caps = list(READONLY_CAPABILITIES)
        if include_mutating:
            caps.append(MUTATING_CAPABILITIES[0])
            if include_batch:
                caps.append(MUTATING_CAPABILITIES[1])
        if include_execution:
            caps.extend(EXECUTION_CAPABILITIES)
        if include_admin:
            caps.extend(ADMIN_CAPABILITIES)
        return caps

    @staticmethod
    def get_capability(name: str) -> Capability:
        from tacp.domain.errors import TacpNotFoundError

        for c in READONLY_CAPABILITIES:
            if c.name == name:
                return c
        for c in MUTATING_CAPABILITIES:
            if c.name == name:
                return c
        for c in EXECUTION_CAPABILITIES:
            if c.name == name:
                return c
        for c in ADMIN_CAPABILITIES:
            if c.name == name:
                return c
        raise TacpNotFoundError(f"Capability not found: {name}")
