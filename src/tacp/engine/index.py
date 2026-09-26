"""Capability, Provider, and Policy Indexing Engine (Phase 14 & 15).

Provides O(1) resolution for:
1. Capability definitions and aliases
2. Provider availability states
3. Policy risk profiles and permission boundaries
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from tacp.backends.base import BackendStatus, BackendType, BaseBackend
from tacp.engine.capability import CapabilityDefinition


class ProviderState(str, Enum):
    """Categorized provider operational state."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    REQUIRES_PERMISSION = "requires_permission"
    DISCONNECTED = "disconnected"

    @classmethod
    def from_backend_status(cls, status: BackendStatus) -> "ProviderState":
        if status == BackendStatus.AVAILABLE:
            return cls.AVAILABLE
        elif status in (
            BackendStatus.PERMISSION_REQUIRED,
            BackendStatus.SHIZUKU_REQUIRED,
            BackendStatus.ROOT_REQUIRED,
        ):
            return cls.REQUIRES_PERMISSION
        elif status == BackendStatus.COMPANION_REQUIRED:
            return cls.DISCONNECTED
        elif status == BackendStatus.DEGRADED:
            return cls.DEGRADED
        return cls.UNAVAILABLE


@dataclass(frozen=True)
class IndexedCapability:
    """Pre-indexed, immutable capability record for O(1) dispatch."""

    id: str
    definition: CapabilityDefinition
    category: str
    privilege_level: str
    supported_backends: Tuple[BackendType, ...]
    handler: Optional[Callable[[BaseBackend, Dict[str, Any]], Dict[str, Any]]]


class ProviderIndex:
    """O(1) provider state store with stratified caching and TTL invalidation."""

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._states: Dict[BackendType, ProviderState] = {}
        self._timestamps: Dict[BackendType, float] = {}

    def get_state(
        self, backend_type: BackendType, backend: Optional[BaseBackend] = None
    ) -> ProviderState:
        now = time.monotonic()
        last = self._timestamps.get(backend_type, 0.0)
        if (now - last) < self.ttl_seconds and backend_type in self._states:
            return self._states[backend_type]

        if backend is not None:
            status = backend.probe(force=False)
            state = ProviderState.from_backend_status(status)
        else:
            state = ProviderState.UNAVAILABLE

        self._states[backend_type] = state
        self._timestamps[backend_type] = now
        return state

    def set_state(self, backend_type: BackendType, state: ProviderState) -> None:
        self._states[backend_type] = state
        self._timestamps[backend_type] = time.monotonic()

    def invalidate(self, backend_type: Optional[BackendType] = None) -> None:
        if backend_type:
            self._states.pop(backend_type, None)
            self._timestamps.pop(backend_type, None)
        else:
            self._states.clear()
            self._timestamps.clear()


class CapabilityIndex:
    """Immutable snapshot index providing O(1) capability lookup and alias resolution."""

    def __init__(self, capabilities: List[CapabilityDefinition]) -> None:
        by_id: Dict[str, IndexedCapability] = {}
        by_name: Dict[str, IndexedCapability] = {}

        for cap in capabilities:
            indexed = IndexedCapability(
                id=cap.id,
                definition=cap,
                category=cap.category,
                privilege_level=cap.privilege_level,
                supported_backends=tuple(cap.supported_backends),
                handler=cap.handler,
            )
            by_id[cap.id] = indexed
            by_name[cap.id] = indexed

            # Pre-index normalized alias forms (tacp_ prefix, underscore)
            by_name[f"tacp_{cap.id}"] = indexed
            underscore_form = cap.id.replace(".", "_")
            by_name[underscore_form] = indexed
            by_name[f"tacp_{underscore_form}"] = indexed

        self._by_id = by_id
        self._by_name = by_name

    def get(self, name: str) -> Optional[IndexedCapability]:
        """O(1) capability lookup handling dot, underscore, and tacp_ prefix."""
        return self._by_name.get(name)

    def contains(self, name: str) -> bool:
        return name in self._by_name

    def all_ids(self) -> Set[str]:
        return set(self._by_id.keys())

    def list_all(self) -> List[IndexedCapability]:
        return list(self._by_id.values())


@dataclass(frozen=True)
class PolicyCapabilityRule:
    """Pre-computed policy categorization and risk tier for O(1) checks."""

    capability: str
    category: str  # "READONLY", "MUTATING", "EXECUTION", "DEVICE", "ADMIN"
    risk_level: str  # "R0", "R1", "R2", "R3"
    allowed_in_lockdown: bool
    allowed_in_remote_readonly: bool
    requires_approval: bool
    required_authority: Optional[str]


class PolicyIndex:
    """O(1) policy index eliminating repetitive regex evaluation and string slicing."""

    def __init__(self) -> None:
        self._rules: Dict[str, PolicyCapabilityRule] = {}
        self._build_default_rules()

    def _build_default_rules(self) -> None:
        # Standard Core Readonly
        core_ro = [
            "system.inspect",
            "system.health",
            "system.version",
            "capabilities.list",
            "workspace.list",
            "workspace.inspect",
            "fs.list",
            "fs.stat",
            "fs.read",
            "fs.search",
            "process.list",
            "process.inspect",
            "audit.recent",
        ]
        for cap in core_ro:
            self._rules[cap] = PolicyCapabilityRule(
                capability=cap,
                category="READONLY",
                risk_level="R0",
                allowed_in_lockdown=True,
                allowed_in_remote_readonly=True,
                requires_approval=False,
                required_authority=None,
            )

        # Integrity verification
        self._rules["audit.verify_integrity"] = PolicyCapabilityRule(
            capability="audit.verify_integrity",
            category="READONLY",
            risk_level="R1",
            allowed_in_lockdown=True,
            allowed_in_remote_readonly=False,
            requires_approval=False,
            required_authority="AUDIT",
        )

        # Core Mutating
        for cap in (
            "workspace.patch",
            "workspace.patch_batch",
            "workspace.rollback",
            "workspace.batch_rollback",
        ):
            self._rules[cap] = PolicyCapabilityRule(
                capability=cap,
                category="MUTATING",
                risk_level="R2",
                allowed_in_lockdown=False,
                allowed_in_remote_readonly=False,
                requires_approval=False,
                required_authority=None,
            )

        # Execution
        for cap in ("execution.request", "execution.inspect", "execution.list", "execution.cancel"):
            self._rules[cap] = PolicyCapabilityRule(
                capability=cap,
                category="EXECUTION",
                risk_level="R3" if cap == "execution.request" else "R1",
                allowed_in_lockdown=False,
                allowed_in_remote_readonly=False,
                requires_approval=False,
                required_authority="EXECUTE",
            )

    def register_device_capability(
        self,
        cap_id: str,
        category: str,
        is_mutating: bool,
    ) -> None:
        """Index a device capability for O(1) policy checking."""
        risk = "R2" if is_mutating else "R0"
        self._rules[cap_id] = PolicyCapabilityRule(
            capability=cap_id,
            category="DEVICE_MUTATING" if is_mutating else "DEVICE_READONLY",
            risk_level=risk,
            allowed_in_lockdown=not is_mutating,
            allowed_in_remote_readonly=not is_mutating,
            requires_approval=False,
            required_authority="ADMIN" if is_mutating else None,
        )

    def get_rule(self, capability: str) -> Optional[PolicyCapabilityRule]:
        return self._rules.get(capability)
