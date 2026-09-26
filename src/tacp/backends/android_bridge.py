"""Android Bridge Companion App Backend Implementation."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from tacp.backends.base import BackendStatus, BackendType, BaseBackend, ExecutionResult
from tacp.backends.companion_transport import CompanionTransport, HttpCompanionTransport


class AndroidBridgeBackend(BaseBackend):
    """Communicates with the TACP Android Bridge companion APK via pluggable CompanionTransport."""

    DEFAULT_PORT = 8766

    def __init__(self, port: int = DEFAULT_PORT, transport: Optional[CompanionTransport] = None) -> None:
        super().__init__(BackendType.ANDROID_BRIDGE)
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.transport = transport or HttpCompanionTransport(port=port)
        self.services_active: Dict[str, bool] = {
            "accessibility": False,
            "media_projection": False,
            "notification_listener": False,
        }
        self.probe()

    def probe(self, force: bool = False) -> BackendStatus:
        now = time.time()
        if not force and (now - self._last_probed < 30.0):
            return self._status

        self._last_probed = now
        try:
            req = urllib.request.Request(f"{self.base_url}/health", method="GET")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    self._available = True
                    self._status = BackendStatus.AVAILABLE
                    self.services_active = data.get("services", {})
                    self._details = f"TACP Android Bridge connected on port {self.port} (services: {list(self.services_active.keys())})"
                    return self._status
        except Exception:
            pass

        self._available = False
        self._status = BackendStatus.COMPANION_REQUIRED
        self._details = "TACP Android Bridge companion app not running on localhost:8766"
        self.services_active = {"accessibility": False, "media_projection": False, "notification_listener": False}
        return self._status

    def is_service_active(self, service_name: str) -> bool:
        return self._available and self.services_active.get(service_name, False)

    def call_bridge(self, endpoint: str, payload: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
        """Make an authenticated request to the Android Bridge via CompanionTransport."""
        if not self._available:
            raise RuntimeError(f"Android Bridge companion service is not currently active on {self.base_url}")

        return self.transport.send_request(endpoint, payload=payload, timeout=timeout)

    def execute(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        input_data: Optional[str] = None,
    ) -> ExecutionResult:
        if not self._available:
            return ExecutionResult(
                exit_code=1,
                stdout="",
                stderr="Error: Android Bridge companion application is not running.",
                duration_ms=0.0,
                backend=self.backend_type,
                metadata={"requirements": ["TACP Android Bridge Companion APK"]},
            )

        start_time = time.perf_counter()
        try:
            res = self.call_bridge("/exec", {"cmd": cmd, "timeout": timeout}, timeout=timeout)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return ExecutionResult(
                exit_code=res.get("exit_code", 0),
                stdout=res.get("stdout", ""),
                stderr=res.get("stderr", ""),
                duration_ms=duration_ms,
                backend=self.backend_type,
                metadata=res.get("metadata", {}),
            )
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return ExecutionResult(
                exit_code=1,
                stdout="",
                stderr=str(exc),
                duration_ms=duration_ms,
                backend=self.backend_type,
            )
