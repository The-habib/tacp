"""System information and health provider for POSIX and Termux."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Dict


class SystemProvider:
    """Provides system diagnostics, architecture, and resource health metrics."""

    @staticmethod
    def _get_storage() -> Dict[str, Any]:
        target = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
        if not Path(target).exists():
            target = str(Path.home())
        usage = shutil.disk_usage(target)
        return {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "total_mb": usage.total // (1024 * 1024),
            "free_mb": usage.free // (1024 * 1024),
            "used_percent": round((usage.used / usage.total) * 100, 1),
        }

    @staticmethod
    def _get_memory() -> Dict[str, Any]:
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            try:
                data = {}
                for line in meminfo.read_text().splitlines():
                    parts = line.split(":")
                    if len(parts) == 2:
                        k = parts[0].strip()
                        v = parts[1].strip().split()[0]
                        if v.isdigit():
                            data[k] = int(v)
                total_kb = data.get("MemTotal", 0)
                free_kb = data.get("MemAvailable", data.get("MemFree", 0))
                return {
                    "total_mb": total_kb // 1024,
                    "free_mb": free_kb // 1024,
                }
            except (OSError, ValueError):
                pass
        return {"total_mb": 0, "free_mb": 0}

    @classmethod
    def get_system_info(cls) -> Dict[str, Any]:
        uname = platform.uname()
        prefix = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
        is_termux = "com.termux" in prefix or Path("/data/data/com.termux").exists()
        storage = cls._get_storage()
        mem = cls._get_memory()

        return {
            "os": uname.system,
            "node": uname.node,
            "release": uname.release,
            "version": uname.version,
            "machine": uname.machine,
            "arch": uname.machine,
            "kernel": uname.release,
            "python_version": sys.version.split()[0],
            "termux": {
                "is_termux": is_termux,
                "version": os.environ.get("TERMUX_VERSION", "0.118.3"),
                "prefix": prefix,
            },
            "memory": mem,
            "storage": storage,
        }

    @classmethod
    def get_health(cls) -> Dict[str, Any]:
        storage = cls._get_storage()
        low_storage = storage["free_mb"] < 250  # Low disk warning if under 250MB
        status = "HEALTHY" if not low_storage else "WARNING"

        return {
            "status": status,
            "storage_healthy": not low_storage,
            "checks": {
                "storage_margin": {
                    "status": "PASS" if not low_storage else "WARN",
                    "free_mb": storage["free_mb"],
                },
            },
        }
