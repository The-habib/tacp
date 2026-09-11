import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from tacp.domain.errors import (
    ErrorCode,
    TacpNotFoundError,
    TacpSecurityError,
    TacpValidationError,
)
from tacp.infrastructure.config import OutputLimits


class ProcessProvider:
    def __init__(self, limits: Optional[OutputLimits] = None) -> None:
        self.limits = limits or OutputLimits()
        self.uid = os.getuid()

    def list_processes(self) -> Dict[str, Any]:
        processes: List[Dict[str, Any]] = []
        truncated = False
        proc_path = Path("/proc")

        if not proc_path.exists():
            return {"processes": [], "total_count": 0, "truncated": False}

        pids = []
        for entry in proc_path.iterdir():
            if entry.name.isdigit():
                try:
                    pids.append(int(entry.name))
                except ValueError:
                    continue

        pids.sort()
        for pid in pids:
            try:
                stat_p = proc_path / str(pid)
                # Sandbox: only list user-owned processes
                if stat_p.stat().st_uid != self.uid:
                    continue

                cmdline = (
                    (stat_p / "cmdline")
                    .read_bytes()
                    .replace(b"\x00", b" ")
                    .decode(errors="ignore")
                    .strip()
                )
                name = (
                    (stat_p / "comm").read_text(errors="ignore").strip()
                    if (stat_p / "comm").exists()
                    else "unknown"
                )

                processes.append(
                    {
                        "pid": pid,
                        "name": name,
                        "cmdline": cmdline[:150],
                    }
                )

                if len(processes) >= self.limits.max_processes:
                    truncated = True
                    break
            except (OSError, ValueError):
                continue

        return {
            "processes": processes,
            "total_count": len(processes),
            "truncated": truncated,
        }

    def inspect_process(self, pid: int) -> Dict[str, Any]:
        if pid <= 0:
            raise TacpValidationError(f"Invalid PID: {pid}")

        proc_dir = Path(f"/proc/{pid}")
        if not proc_dir.exists():
            raise TacpNotFoundError(f"Process PID {pid} not found")

        try:
            stat = proc_dir.stat()
            if stat.st_uid != self.uid:
                raise TacpSecurityError(
                    ErrorCode.NOT_AUTHORIZED,
                    f"Access denied: PID {pid} is not owned by current Termux user",
                )

            cmdline = (
                (proc_dir / "cmdline")
                .read_bytes()
                .replace(b"\x00", b" ")
                .decode(errors="ignore")
                .strip()
            )
            name = (
                (proc_dir / "comm").read_text(errors="ignore").strip()
                if (proc_dir / "comm").exists()
                else "unknown"
            )
            status_text = (
                (proc_dir / "status").read_text(errors="ignore")
                if (proc_dir / "status").exists()
                else ""
            )

            # Extract memory VmRSS from status
            vm_rss = "unknown"
            for line in status_text.splitlines():
                if line.startswith("VmRSS:"):
                    vm_rss = line.split(":", 1)[1].strip()
                    break

            return {
                "pid": pid,
                "name": name,
                "cmdline": cmdline,
                "vm_rss": vm_rss,
                "uid": stat.st_uid,
            }
        except (TacpNotFoundError, TacpSecurityError):
            raise
        except Exception as exc:
            raise TacpSecurityError(
                ErrorCode.PROVIDER_ERROR, f"Failed to inspect PID {pid}: {exc}"
            ) from exc
