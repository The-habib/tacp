"""Handlers for process.* namespace capabilities."""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from tacp.backends.base import BaseBackend


def handle_process_list(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """List running processes accessible to current user."""
    processes: List[Dict[str, Any]] = []

    # First attempt: parse /proc directly (fastest and most accurate)
    try:
        proc_dir = Path("/proc")
        for entry in proc_dir.iterdir():
            if entry.name.isdigit():
                pid = int(entry.name)
                cmdline_file = entry / "cmdline"
                comm_file = entry / "comm"

                name = ""
                if comm_file.exists():
                    try:
                        name = comm_file.read_text().strip()
                    except Exception:
                        pass

                cmdline = ""
                if cmdline_file.exists():
                    try:
                        raw = cmdline_file.read_bytes()
                        cmdline = " ".join(
                            [part.decode("utf-8", "ignore") for part in raw.split(b"\x00") if part]
                        )
                    except Exception:
                        pass

                if name or cmdline:
                    processes.append(
                        {
                            "pid": pid,
                            "name": name or cmdline.split()[0],
                            "command": cmdline or name,
                        }
                    )
    except Exception:
        pass

    # Fallback to ps -A if /proc scan returned few processes
    if len(processes) < 3:
        try:
            p = subprocess.run(["ps", "-A"], capture_output=True, text=True, timeout=2.0)
            if p.returncode == 0:
                processes.clear()
                lines = p.stdout.splitlines()
                for line in lines[1:]:
                    parts = line.split(None, 8)
                    if len(parts) >= 4 and parts[1].isdigit():
                        processes.append(
                            {
                                "pid": int(parts[1]),
                                "name": parts[-1],
                                "command": parts[-1],
                                "user": parts[0],
                            }
                        )
        except Exception:
            pass

    limit = int(params.get("limit", 100))
    return {
        "success": True,
        "count": len(processes),
        "processes": processes[:limit],
    }


def handle_process_inspect(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Inspect status, command line, and metadata of a specific PID."""
    pid = params.get("pid")
    if pid is None:
        return {"success": False, "error": "Missing required parameter 'pid'"}

    pid = int(pid)
    proc_path = Path(f"/proc/{pid}")
    if not proc_path.exists():
        return {"success": False, "error": f"Process {pid} not found or terminated"}

    info: Dict[str, Any] = {"pid": pid, "alive": True}

    # comm
    comm_file = proc_path / "comm"
    if comm_file.exists():
        try:
            info["name"] = comm_file.read_text().strip()
        except Exception:
            pass

    # cmdline
    cmd_file = proc_path / "cmdline"
    if cmd_file.exists():
        try:
            raw = cmd_file.read_bytes()
            info["cmdline"] = [p.decode("utf-8", "ignore") for p in raw.split(b"\x00") if p]
        except Exception:
            pass

    # status
    status_file = proc_path / "status"
    if status_file.exists():
        try:
            st = {}
            for line in status_file.read_text().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    st[k.strip()] = v.strip()
            info["status"] = {
                "state": st.get("State"),
                "ppid": int(st.get("PPid", 0)) if st.get("PPid", "").isdigit() else 0,
                "uid": st.get("Uid"),
                "threads": int(st.get("Threads", 1)) if st.get("Threads", "").isdigit() else 1,
                "vm_size": st.get("VmSize"),
                "vm_rss": st.get("VmRSS"),
            }
        except Exception:
            pass

    return {"success": True, "process": info}


def handle_process_signal(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Send OS signal to target PID."""
    pid = params.get("pid")
    if pid is None:
        return {"success": False, "error": "Missing required parameter 'pid'"}

    sig_num = int(params.get("signal", signal.SIGTERM))
    try:
        os.kill(int(pid), sig_num)
        return {
            "success": True,
            "pid": int(pid),
            "signal": sig_num,
            "message": f"Signal {sig_num} sent successfully",
        }
    except ProcessLookupError:
        return {"success": False, "error": f"Process {pid} does not exist"}
    except PermissionError:
        return {"success": False, "error": f"Permission denied sending signal to PID {pid}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def handle_process_kill(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Force terminate target PID (SIGKILL)."""
    return handle_process_signal(backend, {"pid": params.get("pid"), "signal": signal.SIGKILL})
