"""Root / SU Privilege Backend Implementation."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

from tacp.backends.base import BackendStatus, BackendType, BaseBackend, ExecutionResult


class RootBackend(BaseBackend):
    """Executes superuser commands when device has active root/su."""

    def __init__(self) -> None:
        super().__init__(BackendType.ROOT)
        self.su_path: Optional[str] = None
        self.probe()

    def probe(self, force: bool = False) -> BackendStatus:
        now = time.time()
        if not force and (now - self._last_probed < 60.0):
            return self._status

        self._last_probed = now
        su_paths = [
            "/system/bin/su", "/system/xbin/su", "/sbin/su",
            "/data/local/tmp/su", "/data/data/com.termux/files/usr/bin/su"
        ]
        found_su = None
        for path in su_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                found_su = path
                break

        if not found_su:
            sys_su = shutil.which("su")
            if sys_su and "termux" not in sys_su:
                found_su = sys_su

        if not found_su:
            self._available = False
            self._status = BackendStatus.UNAVAILABLE
            self._details = "No su binary present on device"
            self.su_path = None
            return self._status

        # Test if su functions with genuine UID 0
        try:
            p = subprocess.run([found_su, "-c", "id"], capture_output=True, text=True, timeout=2.0)
            if p.returncode == 0 and "uid=0" in p.stdout:
                self._available = True
                self._status = BackendStatus.AVAILABLE
                self.su_path = found_su
                self._details = "Root execution verified (uid=0)"
                return self._status
        except Exception:
            pass

        self._available = False
        self._status = BackendStatus.ROOT_REQUIRED
        self._details = "Device is not rooted or su rejected authorization"
        self.su_path = None
        return self._status

    def execute(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        input_data: Optional[str] = None,
    ) -> ExecutionResult:
        if not self._available or not self.su_path:
            return ExecutionResult(
                exit_code=1,
                stdout="",
                stderr="Error: Root backend unavailable. Device is not rooted.",
                duration_ms=0.0,
                backend=self.backend_type,
                metadata={"requirements": ["Root / SU binary"]},
            )

        cmd_str = " ".join(cmd)
        su_cmd = [self.su_path, "-c", cmd_str]
        start_time = time.perf_counter()
        timed_out = False
        try:
            proc = subprocess.run(
                su_cmd,
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
            stderr = f"Root command timed out after {timeout} seconds"
        except Exception as exc:
            exit_code = 1
            stdout = ""
            stderr = f"Root execution error: {exc}"

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return ExecutionResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            timed_out=timed_out,
            backend=self.backend_type,
        )
