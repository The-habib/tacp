"""Termux:API Backend Implementation."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

from tacp.backends.base import BackendStatus, BackendType, BaseBackend, ExecutionResult


class TermuxApiBackend(BaseBackend):
    """Integrates with Termux:API commands and Android framework bridge."""

    def __init__(self) -> None:
        super().__init__(BackendType.TERMUX_API)
        self.cli_installed: bool = False
        self.apk_installed: bool = False
        self.probe()

    def probe(self, force: bool = False) -> BackendStatus:
        now = time.time()
        if not force and (now - self._last_probed < 60.0):
            return self._status

        self._last_probed = now
        self.cli_installed = bool(shutil.which("termux-battery-status"))

        # Check if com.termux.api APK is installed on Android
        self.apk_installed = False
        pm_bin = "/system/bin/pm" if os.path.exists("/system/bin/pm") else "pm"
        try:
            p = subprocess.run([pm_bin, "list", "packages", "com.termux.api"], capture_output=True, text=True, timeout=2.0)
            if p.returncode == 0 and "package:com.termux.api" in p.stdout:
                self.apk_installed = True
        except Exception:
            pass

        if self.cli_installed and self.apk_installed:
            self._available = True
            self._status = BackendStatus.AVAILABLE
            self._details = "Termux:API fully operational (CLI & APK verified)"
        elif self.cli_installed and not self.apk_installed:
            self._available = False
            self._status = BackendStatus.COMPANION_REQUIRED
            self._details = "Termux:API CLI is installed, but com.termux.api APK is not installed on Android host"
        else:
            self._available = False
            self._status = BackendStatus.UNAVAILABLE
            self._details = "termux-api package is not installed in Termux"

        return self._status

    def execute(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 5.0,
        input_data: Optional[str] = None,
    ) -> ExecutionResult:
        if not self.cli_installed:
            return ExecutionResult(
                exit_code=127,
                stdout="",
                stderr="Error: Termux:API CLI package is not installed in Termux (run 'pkg install termux-api')",
                duration_ms=0.0,
                backend=self.backend_type,
            )

        if not self.apk_installed:
            return ExecutionResult(
                exit_code=1,
                stdout="",
                stderr="Error: Termux:API companion APK (com.termux.api) is not installed on Android. Please install it from F-Droid or GitHub to use Termux hardware APIs.",
                duration_ms=0.0,
                backend=self.backend_type,
                metadata={"requirements": ["com.termux.api APK"]},
            )

        start_time = time.perf_counter()
        timed_out = False
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                input=input_data,
                timeout=min(timeout, 8.0),
            )
            exit_code = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = -1
            stdout = ""
            stderr = "Termux:API call timed out waiting for companion app broadcast response"
        except Exception as exc:
            exit_code = 1
            stdout = ""
            stderr = f"Termux:API execution error: {exc}"

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return ExecutionResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            timed_out=timed_out,
            backend=self.backend_type,
        )
