"""Capability definition and metadata schema for TACP device control."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from tacp.backends.base import BackendStatus, BackendType


class RiskClassification(str, enum.Enum):
    READ_ONLY = "READ_ONLY"
    LOW_RISK_WRITE = "LOW_RISK_WRITE"
    HIGH_RISK_WRITE = "HIGH_RISK_WRITE"
    EXECUTION = "EXECUTION"
    PRIVILEGED = "PRIVILEGED"


@dataclass
class CapabilityParameter:
    """Parameter schema definition for a capability."""

    name: str
    type_name: str
    description: str
    required: bool = False
    default: Any = None
    enum: Optional[List[Any]] = None


@dataclass
class CapabilityDefinition:
    """Full architectural specification of a device capability."""

    id: str
    name: str
    description: str
    category: str
    supported_backends: List[BackendType]
    privilege_level: str = "user"  # "user", "shell", "companion", "root"
    mutating: bool = False
    streaming: bool = False
    events: bool = False
    parameters: Dict[str, Any] = field(default_factory=dict)
    return_schema: Dict[str, Any] = field(default_factory=dict)
    min_sdk: Optional[int] = None
    dependencies: List[str] = field(default_factory=list)
    setup_instructions: str = ""
    handler: Optional[Callable[..., Any]] = None
    explicit_risk: Optional[RiskClassification] = None

    @property
    def risk_classification(self) -> str:
        if self.explicit_risk:
            return self.explicit_risk.value
        if self.privilege_level in ("root", "shizuku") or self.id in (
            "package.install",
            "package.uninstall",
            "input.tap",
            "input.key",
        ):
            return RiskClassification.PRIVILEGED.value
        if self.category == "shell" or self.id in (
            "execution.request",
            "process.kill",
            "process.signal",
            "app.launch",
            "automation.start",
            "tasks.cancel",
        ):
            return RiskClassification.EXECUTION.value
        if self.mutating and (
            self.category in ("filesystem", "screen", "camera", "microphone", "location")
            or "delete" in self.id
            or "unzip" in self.id
        ):
            return RiskClassification.HIGH_RISK_WRITE.value
        if self.mutating:
            return RiskClassification.LOW_RISK_WRITE.value
        return RiskClassification.READ_ONLY.value

    def to_mcp_tool_schema(self) -> Dict[str, Any]:
        """Convert capability definition to standard MCP Tool schema."""
        properties: Dict[str, Any] = {}
        required: List[str] = []

        for p_name, p_def in self.parameters.items():
            prop: Dict[str, Any] = {
                "type": p_def.get("type", "string"),
                "description": p_def.get("description", ""),
            }
            if "enum" in p_def:
                prop["enum"] = p_def["enum"]
            if "default" in p_def:
                prop["default"] = p_def["default"]
            properties[p_name] = prop

            if p_def.get("required", False):
                required.append(p_name)

        input_schema: Dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            input_schema["required"] = required

        return {
            "name": self.id,
            "description": f"[{self.category.upper()}] {self.description}",
            "inputSchema": input_schema,
        }

    def to_dict(
        self,
        active_backend: Optional[BackendType] = None,
        availability: Optional[BackendStatus] = None,
    ) -> Dict[str, Any]:
        """Serialize capability for capabilities.list and doctor reports."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "active_backend": active_backend.value if active_backend else None,
            "supported_backends": [b.value for b in self.supported_backends],
            "availability": availability.value if availability else "unknown",
            "privilege_level": self.privilege_level,
            "mutating": self.mutating,
            "streaming": self.streaming,
            "events": self.events,
            "min_sdk": self.min_sdk,
            "dependencies": self.dependencies,
            "setup_instructions": self.setup_instructions,
            "parameters": self.parameters,
            "return_schema": self.return_schema,
            "risk_classification": self.risk_classification,
        }
