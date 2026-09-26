"""Centralized Backend Manager for TACP."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from tacp.backends.adb import AdbBackend
from tacp.backends.android_bridge import AndroidBridgeBackend
from tacp.backends.android_shell import AndroidShellBackend
from tacp.backends.base import BackendStatus, BackendType, BaseBackend, ExecutionResult
from tacp.backends.root import RootBackend
from tacp.backends.shizuku import ShizukuBackend
from tacp.backends.termux import TermuxBackend
from tacp.backends.termux_api import TermuxApiBackend

logger = logging.getLogger(__name__)


class BackendManager:
    """Coordinates detection, health, and execution routing across all platform backends."""

    _default_instance: Optional["BackendManager"] = None

    @classmethod
    def get_default(cls) -> "BackendManager":
        if cls._default_instance is None:
            cls._default_instance = cls()
        return cls._default_instance

    def __init__(self) -> None:
        self.termux = TermuxBackend()
        self.android_shell = AndroidShellBackend()
        self.termux_api = TermuxApiBackend()
        self.shizuku = ShizukuBackend()
        self.root = RootBackend()
        self.adb = AdbBackend()
        self.android_bridge = AndroidBridgeBackend()

        self._backends: Dict[BackendType, BaseBackend] = {
            BackendType.TERMUX: self.termux,
            BackendType.ANDROID_SHELL: self.android_shell,
            BackendType.TERMUX_API: self.termux_api,
            BackendType.SHIZUKU: self.shizuku,
            BackendType.ROOT: self.root,
            BackendType.ADB: self.adb,
            BackendType.ANDROID_BRIDGE: self.android_bridge,
        }

    def probe_all(self, force: bool = False) -> Dict[str, Dict[str, Any]]:
        """Probe all backends and return full health & status dictionary."""
        results = {}
        for b_type, b_inst in self._backends.items():
            b_inst.probe(force=force)
            results[b_type.value] = b_inst.get_info()
        return results

    def get_backend(self, backend_type: BackendType) -> Optional[BaseBackend]:
        """Fetch a specific backend by type."""
        return self._backends.get(backend_type)

    def resolve_best_backend(self, candidate_types: List[BackendType]) -> Optional[BaseBackend]:
        """Resolve the first genuinely available backend from a list of prioritized candidates."""
        for c in candidate_types:
            backend = self._backends.get(c)
            if backend and backend.is_available:
                return backend
        return None

    def execute_best(
        self,
        candidate_types: List[BackendType],
        cmd: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        input_data: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute command using the best available backend among candidates."""
        resolved = self.resolve_best_backend(candidate_types)
        if resolved:
            return resolved.execute(cmd, cwd=cwd, env=env, timeout=timeout, input_data=input_data)

        # None of the candidates are available; report requirement from first candidate
        primary = candidate_types[0] if candidate_types else BackendType.TERMUX
        backend_obj = self._backends.get(primary)
        status_msg = backend_obj.details if backend_obj else "No suitable backend available"
        return ExecutionResult(
            exit_code=1,
            stdout="",
            stderr=f"Capability unavailable: {status_msg}",
            duration_ms=0.0,
            backend=primary,
            metadata={"candidate_backends": [c.value for c in candidate_types]},
        )
