"""ADB Execution Backend Implementation."""

from __future__ import annotations

import shutil
import subprocess
import time
from typing import Dict, List, Optional

from tacp.backends.base import BackendStatus, BackendType, BaseBackend, ExecutionResult


class AdbBackend(BaseBackend):
    """Executes commands through local ADB daemon or wireless debugging interface."""

    def __init__(self) -> None:
        super().__init__(BackendType.ADB)
        self.adb_bin: Optional[str] = None
        self.probe()

    def probe(self, force: bool = False) -> BackendStatus:
        now = time.time()
        if not force and (now - self._last_probed < 60.0):
            return self._status

        self._last_probed = now
        self.adb_bin = shutil.which("adb")
        if not self.adb_bin:
            self._available = False
            self._status = BackendStatus.UNAVAILABLE
            self._details = (
                "adb binary not installed in Termux (install via 'pkg install android-tools')"
            )
            return self._status

        try:
            p = subprocess.run(
                [self.adb_bin, "devices"], capture_output=True, text=True, timeout=2.0
            )
            lines = [
                line
                for line in p.stdout.splitlines()
                if line and not line.startswith("List of devices")
            ]
            active_devices = [dev_line for dev_line in lines if "\tdevice" in dev_line]
            if active_devices:
                self._available = True
                self._status = BackendStatus.AVAILABLE
                self._details = f"ADB connected to {len(active_devices)} device(s)"
                return self._status
        except Exception:
            pass

        self._available = False
        self._status = BackendStatus.PERMISSION_REQUIRED
        self._details = (
            "adb binary present, but no authorized device connected (pair via Wireless Debugging)"
        )
        return self._status

    def execute(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        input_data: Optional[str] = None,
    ) -> ExecutionResult:
        if not self._available or not self.adb_bin:
            return ExecutionResult(
                exit_code=1,
                stdout="",
                stderr="Error: ADB backend unavailable. Pair and connect via Wireless Debugging ('adb connect localhost:PORT').",
                duration_ms=0.0,
                backend=self.backend_type,
                metadata={"requirements": ["ADB Wireless Debugging"]},
            )

        adb_cmd = [self.adb_bin, "shell"] + cmd
        start_time = time.perf_counter()
        timed_out = False
        try:
            proc = subprocess.run(
                adb_cmd,
                capture_output=True,
                text=True,
                input=input_data,
                timeout=timeout,
            )
            exit_code = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = -1
            stdout = ""
            stderr = f"ADB command timed out after {timeout} seconds"
        except Exception as exc:
            exit_code = 1
            stdout = ""
            stderr = f"ADB execution error: {exc}"

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return ExecutionResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            timed_out=timed_out,
            backend=self.backend_type,
        )
