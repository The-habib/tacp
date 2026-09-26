"""Handlers for shell.* namespace capabilities."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict

from tacp.backends.base import BaseBackend


def handle_shell_exec(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute arbitrary command on the host shell."""
    cmd = params.get("command")
    if not cmd:
        return {"success": False, "error": "Missing required parameter 'command'"}

    args = params.get("args", [])
    if isinstance(cmd, str):
        full_cmd = [cmd] + [str(a) for a in args]
    else:
        full_cmd = list(cmd) + [str(a) for a in args]

    cwd = params.get("cwd")
    env = params.get("env")
    timeout = float(params.get("timeout", 30.0))
    stdin = params.get("stdin")

    res = backend.execute(full_cmd, cwd=cwd, env=env, timeout=timeout, input_data=stdin)
    return {
        "success": res.success,
        "exit_code": res.exit_code,
        "stdout": res.stdout,
        "stderr": res.stderr,
        "duration_ms": res.duration_ms,
        "timed_out": res.timed_out,
        "backend": res.backend.value,
    }


def handle_shell_which(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Locate binary executable across PATH and standard system paths."""
    binary = params.get("binary")
    if not binary:
        return {"success": False, "error": "Missing required parameter 'binary'"}

    # Check PATH
    loc = shutil.which(binary)
    if loc:
        return {"success": True, "binary": binary, "found": True, "path": loc, "source": "PATH"}

    # Check known Android paths
    for sp in ["/system/bin", "/system/xbin", "/vendor/bin", "/apex/com.android.runtime/bin"]:
        p = Path(sp) / binary
        if p.exists() and os.access(p, os.X_OK):
            return {"success": True, "binary": binary, "found": True, "path": str(p), "source": "system"}

    return {"success": True, "binary": binary, "found": False, "path": None}


def handle_shell_env(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Get current environment variables with secrets scrubbed."""
    scrubbed = {}
    sensitive_keys = {"token", "key", "secret", "password", "auth", "credential", "bearer"}
    for k, v in os.environ.items():
        if any(s in k.lower() for s in sensitive_keys):
            scrubbed[k] = "[REDACTED]"
        else:
            scrubbed[k] = v
    return {"success": True, "environment": scrubbed}


def handle_shell_pwd(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Return current working directory."""
    return {"success": True, "cwd": os.getcwd()}
