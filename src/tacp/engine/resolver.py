"""Dynamic Multi-Backend Capability Resolver for TACP."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from tacp.backends.base import BackendStatus, BaseBackend
from tacp.backends.manager import BackendManager
from tacp.engine.capability import CapabilityDefinition

logger = logging.getLogger(__name__)


class CapabilityResolver:
    """Selects and binds the optimal execution backend for any device capability."""

    def __init__(self, backend_manager: BackendManager) -> None:
        self.backend_manager = backend_manager
        self._cache: Dict[str, Tuple[Optional[BaseBackend], BackendStatus, str]] = {}

    def invalidate_cache(self) -> None:
        """Clear cached backend resolution decisions."""
        self._cache.clear()

    def resolve(
        self, cap: CapabilityDefinition, force: bool = False
    ) -> Tuple[Optional[BaseBackend], BackendStatus, str]:
        """Resolve the best available backend for a capability or return requirement reason."""
        if not force and cap.id in self._cache:
            cached_backend, status, reason = self._cache[cap.id]
            if cached_backend and cached_backend.is_available:
                return cached_backend, status, reason
            elif cached_backend is None:
                return None, status, reason

        best_unavail_status = BackendStatus.UNAVAILABLE
        best_unavail_details = cap.setup_instructions or "No backend available"

        for b_type in cap.supported_backends:
            backend = self.backend_manager.get_backend(b_type)
            if not backend:
                continue

            if backend.is_available:
                decision = (backend, BackendStatus.AVAILABLE, f"Resolved via {backend.name}")
                self._cache[cap.id] = decision
                return decision

            # Capture the most informative unavailability status
            if backend.status in (
                BackendStatus.COMPANION_REQUIRED,
                BackendStatus.SHIZUKU_REQUIRED,
                BackendStatus.ROOT_REQUIRED,
                BackendStatus.PERMISSION_REQUIRED,
            ):
                best_unavail_status = backend.status
                best_unavail_details = backend.details or cap.setup_instructions

        unavail_decision = (None, best_unavail_status, best_unavail_details)
        self._cache[cap.id] = unavail_decision
        return unavail_decision

    def execute(self, cap: CapabilityDefinition, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a capability through its resolved backend and handler with structured error protection."""
        backend, status, reason = self.resolve(cap)

        if status != BackendStatus.AVAILABLE or backend is None:
            return {
                "success": False,
                "capability": cap.id,
                "status": status.value,
                "error": f"Capability '{cap.id}' is unavailable: {reason}",
                "dependencies": cap.dependencies,
                "setup_instructions": cap.setup_instructions,
            }

        # If custom handler registered, run handler
        if cap.handler is not None:
            try:
                result = cap.handler(backend, params)
                if isinstance(result, dict):
                    if "success" not in result:
                        result["success"] = True
                    return result
                return {"success": True, "result": result}
            except Exception as exc:
                return {
                    "success": False,
                    "capability": cap.id,
                    "backend": backend.name,
                    "error": f"Handler execution failed: {exc}",
                }

        return {
            "success": False,
            "capability": cap.id,
            "backend": backend.name,
            "error": "No implementation handler registered for capability",
        }
