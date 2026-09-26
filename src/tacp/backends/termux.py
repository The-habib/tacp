"""Termux Native Process Execution Backend."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

from tacp.backends.base import BackendStatus, BackendType, BaseBackend, ExecutionResult


class TermuxBackend(BaseBackend):
    """Executes commands inside the local Termux environment."""

    def __init__(self) -> None:
        super().__init__(BackendType.TERMUX)
        self.prefix = Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"))
        self.home = Path(os.environ.get("HOME", "/data/data/com.termux/files/home"))
        self.probe()

    def probe(self, force: bool = False) -> BackendStatus:
        now = time.time()
        if not force and (now - self._last_probed < 60.0):
            return self._status

        self._last_probed = now
        # Check if running in Termux
        if self.prefix.exists() and (self.prefix / "bin").exists():
            self._available = True
            self._status = BackendStatus.AVAILABLE
            self._details = f"Termux userspace active (prefix: {self.prefix}, uid: {os.getuid()})"
        else:
            self._available = True
            self._status = BackendStatus.AVAILABLE
            self._details = f"Standard POSIX userspace (uid: {os.getuid()})"
        return self._status

    def execute(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        input_data: Optional[str] = None,
    ) -> ExecutionResult:
        if not cmd:
            return ExecutionResult(
                exit_code=1,
                stdout="",
                stderr="Error: Empty command specified",
                duration_ms=0.0,
                backend=self.backend_type,
            )

        # Resolve binary path
        executable = cmd[0]
        full_bin = shutil.which(executable)
        if not full_bin and (self.prefix / "bin" / executable).exists():
            full_bin = str(self.prefix / "bin" / executable)

        final_cmd = [full_bin or executable] + cmd[1:]

        # Merge environment
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        # Ensure PATH includes Termux and system bins
        current_path = merged_env.get("PATH", "")
        extra_paths = [str(self.prefix / "bin"), "/system/bin", "/system/xbin"]
        for ep in extra_paths:
            if ep not in current_path:
                current_path = f"{current_path}:{ep}"
        merged_env["PATH"] = current_path

        start_time = time.perf_counter()
        timed_out = False
        try:
            proc = subprocess.run(
                final_cmd,
                cwd=cwd or str(self.home),
                env=merged_env,
                capture_output=True,
                text=True,
                input=input_data,
                timeout=timeout,
                shell=False,
            )
            exit_code = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = -1
            stdout = exc.stdout or "" if isinstance(exc.stdout, str) else ""
            stderr = f"Command timed out after {timeout} seconds"
        except FileNotFoundError as exc:
            exit_code = 127
            stdout = ""
            stderr = f"Command not found: {executable} ({exc})"
        except PermissionError as exc:
            exit_code = 126
            stdout = ""
            stderr = f"Permission denied: {executable} ({exc})"
        except Exception as exc:
            exit_code = 1
            stdout = ""
            stderr = f"Execution error: {exc}"

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return ExecutionResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            timed_out=timed_out,
            backend=self.backend_type,
            metadata={"executable": full_bin or executable, "cwd": cwd or str(self.home)},
        )
