"""Base definitions for TACP execution backends."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class BackendType(str, enum.Enum):
    TERMUX = "termux"
    ANDROID_SHELL = "android_shell"
    TERMUX_API = "termux_api"
    SHIZUKU = "shizuku"
    ROOT = "root"
    ADB = "adb"
    ANDROID_BRIDGE = "android_bridge"
    ACCESSIBILITY = "accessibility"
    MEDIA_PROJECTION = "media_projection"
    LINUX = "linux"


class BackendStatus(str, enum.Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    PERMISSION_REQUIRED = "permission_required"
    COMPANION_REQUIRED = "companion_required"
    ROOT_REQUIRED = "root_required"
    SHIZUKU_REQUIRED = "shizuku_required"
    UNSUPPORTED = "unsupported"
    DEGRADED = "degraded"
    ERROR = "error"


@dataclass
class ExecutionResult:
    """Structured result returned by any backend execution."""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False
    backend: BackendType = BackendType.TERMUX
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "timed_out": self.timed_out,
            "backend": self.backend.value,
            "metadata": self.metadata,
        }


class BaseBackend:
    """Abstract base class for all execution backends."""

    def __init__(self, backend_type: BackendType) -> None:
        self.backend_type = backend_type
        self._available: bool = False
        self._status: BackendStatus = BackendStatus.UNAVAILABLE
        self._details: str = ""
        self._last_probed: float = 0.0

    @property
    def name(self) -> str:
        return self.backend_type.value

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def status(self) -> BackendStatus:
        return self._status

    @property
    def details(self) -> str:
        return self._details

    def probe(self, force: bool = False) -> BackendStatus:
        """Probe environment to check if this backend is currently functional."""
        raise NotImplementedError

    def execute(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        input_data: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute a command via this backend."""
        raise NotImplementedError

    def get_info(self) -> Dict[str, Any]:
        """Return structured backend telemetry and status."""
        return {
            "backend": self.backend_type.value,
            "available": self._available,
            "status": self._status.value,
            "details": self._details,
            "last_probed": self._last_probed,
        }
