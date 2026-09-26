"""Android Shell (/system/bin) Execution Backend."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from tacp.backends.base import BackendStatus, BackendType, BaseBackend, ExecutionResult


class AndroidShellBackend(BaseBackend):
    """Executes standard Android platform utilities from /system/bin and /system/xbin."""

    KNOWN_SYSTEM_BINS = [
        "getprop", "pm", "am", "cmd", "dumpsys", "logcat", "screencap",
        "input", "settings", "toybox", "df", "sh", "top", "ps", "ip"
    ]

    def __init__(self) -> None:
        super().__init__(BackendType.ANDROID_SHELL)
        self._available_bins: Dict[str, str] = {}
        self.probe()

    def probe(self, force: bool = False) -> BackendStatus:
        now = time.time()
        if not force and (now - self._last_probed < 60.0):
            return self._status

        self._last_probed = now
        self._available_bins.clear()

        system_paths = ["/system/bin", "/system/xbin", "/apex/com.android.runtime/bin"]
        for b in self.KNOWN_SYSTEM_BINS:
            # Check system paths first
            found = None
            for sp in system_paths:
                candidate = Path(sp) / b
                if candidate.exists() and os.access(candidate, os.X_OK):
                    found = str(candidate)
                    break
            if not found:
                sys_which = shutil.which(b)
                if sys_which and ("/system" in sys_which or "/apex" in sys_which):
                    found = sys_which
            if found:
                self._available_bins[b] = found

        if self._available_bins:
            self._available = True
            self._status = BackendStatus.AVAILABLE
            self._details = f"Android /system/bin utilities active ({len(self._available_bins)} verified tools)"
        else:
            self._available = False
            self._status = BackendStatus.UNAVAILABLE
            self._details = "No accessible Android /system/bin binaries found"

        return self._status

    def is_tool_available(self, tool_name: str) -> bool:
        return tool_name in self._available_bins

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

        binary_name = cmd[0]
        # Resolve full binary path if in known system bins
        full_bin = self._available_bins.get(binary_name)
        if not full_bin:
            for sp in ["/system/bin", "/system/xbin"]:
                p = Path(sp) / binary_name
                if p.exists() and os.access(p, os.X_OK):
                    full_bin = str(p)
                    break

        if not full_bin:
            return ExecutionResult(
                exit_code=127,
                stdout="",
                stderr=f"Error: Android shell utility '{binary_name}' not accessible in /system/bin",
                duration_ms=0.0,
                backend=self.backend_type,
            )

        final_cmd = [full_bin] + cmd[1:]
        start_time = time.perf_counter()
        timed_out = False

        # Set up clean Android environment
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)
        exec_env["PATH"] = "/system/bin:/system/xbin:" + exec_env.get("PATH", "")

        try:
            proc = subprocess.run(
                final_cmd,
                cwd=cwd or "/data/data/com.termux/files/home",
                env=exec_env,
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
        except PermissionError as exc:
            exit_code = 126
            stdout = ""
            stderr = f"Android security permission denied: {binary_name} ({exc})"
        except Exception as exc:
            exit_code = 1
            stdout = ""
            stderr = f"Android shell execution error: {exc}"

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return ExecutionResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            timed_out=timed_out,
            backend=self.backend_type,
            metadata={"system_binary": full_bin},
        )
