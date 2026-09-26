"""Shizuku Privilege Backend Implementation."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Dict, List, Optional

from tacp.backends.base import BackendStatus, BackendType, BaseBackend, ExecutionResult


class ShizukuBackend(BaseBackend):
    """Executes privileged commands via Shizuku (UID 2000 shell or root)."""

    def __init__(self) -> None:
        super().__init__(BackendType.SHIZUKU)
        self.rish_path: Optional[str] = None
        self.server_running: bool = False
        self.probe()

    def probe(self, force: bool = False) -> BackendStatus:
        now = time.time()
        if not force and (now - self._last_probed < 60.0):
            return self._status

        self._last_probed = now
        self.rish_path = shutil.which("rish") or "/data/data/com.termux/files/usr/bin/rish"
        rish_exists = os.path.exists(self.rish_path) and os.access(self.rish_path, os.X_OK)

        # Check running process
        self.server_running = False
        try:
            p = subprocess.run(["ps", "-A"], capture_output=True, text=True, timeout=2.0)
            if p.returncode == 0 and (
                "shizuku" in p.stdout.lower() or "moe.shizuku" in p.stdout.lower()
            ):
                self.server_running = True
        except Exception:
            pass

        if not rish_exists and not self.server_running:
            self._available = False
            self._status = BackendStatus.UNAVAILABLE
            self._details = "Shizuku server is not running and rish CLI is not installed"
            return self._status

        if rish_exists:
            try:
                p = subprocess.run(
                    [self.rish_path, "-c", "id"], capture_output=True, text=True, timeout=2.0
                )
                if p.returncode == 0:
                    self._available = True
                    self._status = BackendStatus.AVAILABLE
                    self._details = f"Shizuku execution verified: {p.stdout.strip()}"
                    return self._status
            except Exception:
                pass

        self._available = False
        self._status = BackendStatus.SHIZUKU_REQUIRED
        self._details = "Shizuku process detected or rish present, but execution not authorized"
        return self._status

    def execute(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        input_data: Optional[str] = None,
    ) -> ExecutionResult:
        if not self._available or not self.rish_path:
            return ExecutionResult(
                exit_code=1,
                stdout="",
                stderr="Error: Shizuku backend unavailable. Start Shizuku app and authorize Termux using 'rish'.",
                duration_ms=0.0,
                backend=self.backend_type,
                metadata={"requirements": ["Shizuku Service", "rish"]},
            )

        cmd_str = " ".join(cmd)
        rish_cmd = [self.rish_path, "-c", cmd_str]
        start_time = time.perf_counter()
        timed_out = False
        try:
            proc = subprocess.run(
                rish_cmd,
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
            stderr = f"Shizuku command timed out after {timeout} seconds"
        except Exception as exc:
            exit_code = 1
            stdout = ""
            stderr = f"Shizuku execution error: {exc}"

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return ExecutionResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            timed_out=timed_out,
            backend=self.backend_type,
        )
