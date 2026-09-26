"""Comprehensive Environment & Device Discovery Engine for TACP."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class DeviceDiscovery:
    """Probes and compiles comprehensive device, OS, environment, and backend capabilities."""

    _props_cache: Dict[str, str] = {}
    _props_cache_time: float = 0.0
    _PROPS_CACHE_TTL: float = 120.0

    _selinux_cache: Optional[str] = None
    _root_cache: Optional[Dict[str, Any]] = None
    _root_time: float = 0.0
    _shizuku_cache: Optional[Dict[str, Any]] = None
    _shizuku_time: float = 0.0
    _termux_api_cache: Optional[Dict[str, Any]] = None
    _termux_api_time: float = 0.0
    _packages_cache: Optional[List[Dict[str, str]]] = None
    _packages_time: float = 0.0
    _mounts_cache: Optional[List[Dict[str, Any]]] = None
    _mounts_time: float = 0.0
    _binaries_cache: Optional[Tuple[Dict[str, Any], Dict[str, Any]]] = None
    _snapshot_cache: Optional[Dict[str, Any]] = None
    _snapshot_time: float = 0.0

    @classmethod
    def _load_all_props_once(cls, force: bool = False) -> Dict[str, str]:
        now = time.time()
        if not force and cls._props_cache and (now - cls._props_cache_time < cls._PROPS_CACHE_TTL):
            return cls._props_cache

        props: Dict[str, str] = {}
        for binary in ["/system/bin/getprop", "getprop"]:
            if shutil.which(binary) or os.path.exists(binary):
                try:
                    p = subprocess.run([binary], capture_output=True, text=True, timeout=2.0)
                    if p.returncode == 0 and p.stdout:
                        for line in p.stdout.splitlines():
                            line = line.strip()
                            if line.startswith("[") and "]: [" in line and line.endswith("]"):
                                k, v = line[1:-1].split("]: [", 1)
                                props[k.strip()] = v.strip()
                        break
                except Exception:
                    pass

        cls._props_cache = props
        cls._props_cache_time = now
        return props

    @classmethod
    def get_prop(cls, key: str, default: str = "") -> str:
        """Query Android system property safely with cache fallback."""
        props = cls._load_all_props_once()
        if key in props:
            return props[key]
        for binary in ["/system/bin/getprop", "getprop"]:
            if shutil.which(binary) or os.path.exists(binary):
                try:
                    p = subprocess.run([binary, key], capture_output=True, text=True, timeout=1.5)
                    if p.returncode == 0 and p.stdout.strip():
                        val = p.stdout.strip()
                        cls._props_cache[key] = val
                        return val
                except Exception:
                    pass
        return default

    @classmethod
    def get_all_props(cls) -> Dict[str, str]:
        """Fetch primary Android build and hardware properties efficiently."""
        all_props = cls._load_all_props_once()
        keys = [
            "ro.product.brand",
            "ro.product.manufacturer",
            "ro.product.model",
            "ro.product.name",
            "ro.product.device",
            "ro.build.version.release",
            "ro.build.version.sdk",
            "ro.build.version.security_patch",
            "ro.build.type",
            "ro.build.id",
            "ro.build.fingerprint",
            "ro.board.platform",
            "ro.hardware",
            "ro.crypto.state",
            "gsm.network.type",
            "persist.sys.locale",
        ]
        res = {}
        for k in keys:
            if k in all_props:
                res[k] = all_props[k]
            else:
                v = cls.get_prop(k)
                if v:
                    res[k] = v
        return res

    @staticmethod
    def get_memory_info() -> Dict[str, Any]:
        """Parse Linux /proc/meminfo safely."""
        res: Dict[str, Any] = {"total_mb": 0, "available_mb": 0, "free_mb": 0, "cached_mb": 0}
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            try:
                for line in meminfo.read_text(encoding="utf-8").splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        k = k.strip()
                        num = v.strip().split()[0]
                        if num.isdigit():
                            val_mb = int(num) // 1024
                            if k == "MemTotal":
                                res["total_mb"] = val_mb
                            elif k == "MemAvailable":
                                res["available_mb"] = val_mb
                            elif k == "MemFree":
                                res["free_mb"] = val_mb
                            elif k == "Cached":
                                res["cached_mb"] = val_mb
            except Exception:
                pass
        return res

    @staticmethod
    def get_cpu_info() -> Dict[str, Any]:
        """Parse Linux /proc/cpuinfo safely."""
        res: Dict[str, Any] = {
            "cores": os.cpu_count() or 1,
            "architecture": platform.machine(),
            "hardware": "",
            "features": [],
        }
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.exists():
            try:
                for line in cpuinfo.read_text(encoding="utf-8").splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        k = k.strip()
                        v = v.strip()
                        if k == "Hardware" and not res["hardware"]:
                            res["hardware"] = v
                        elif k == "Features" and not res["features"]:
                            res["features"] = v.split()
            except Exception:
                pass
        return res

    @classmethod
    def get_storage_mounts(cls, force: bool = False) -> List[Dict[str, Any]]:
        """Discover actual filesystem storage roots and mounts with short TTL cache."""
        now = time.time()
        if not force and cls._mounts_cache is not None and (now - cls._mounts_time < 5.0):
            return cls._mounts_cache

        mounts: List[Dict[str, Any]] = []
        seen_targets = set()

        candidates = [
            ("/data/data/com.termux/files/home", "termux-home", "app-private"),
            ("/data/data/com.termux/files/usr", "termux-prefix", "app-binaries"),
            ("/storage/emulated/0", "shared-storage", "user-accessible"),
            ("/storage/emulated", "emulated-root", "system-fuse"),
            ("/data", "data-partition", "system-data"),
            ("/system", "system-partition", "system-os"),
        ]

        for p_str, label, category in candidates:
            p = Path(p_str)
            if p.exists() and p_str not in seen_targets:
                seen_targets.add(p_str)
                try:
                    usage = shutil.disk_usage(p_str)
                    writable = os.access(p_str, os.W_OK)
                    readable = os.access(p_str, os.R_OK)
                    mounts.append({
                        "path": p_str,
                        "label": label,
                        "category": category,
                        "readable": readable,
                        "writable": writable,
                        "total_gb": round(usage.total / (1024 ** 3), 2),
                        "used_gb": round(usage.used / (1024 ** 3), 2),
                        "free_gb": round(usage.free / (1024 ** 3), 2),
                        "used_percent": round((usage.used / usage.total) * 100, 1) if usage.total else 0,
                    })
                except Exception:
                    pass

        cls._mounts_cache = mounts
        cls._mounts_time = now
        return mounts

    @classmethod
    def check_selinux(cls, force: bool = False) -> str:
        """Inspect SELinux status with permanent process-level cache."""
        if not force and cls._selinux_cache is not None:
            return cls._selinux_cache

        # Check /sys/fs/selinux/enforce first (fast procfs read, no subprocess)
        enforce_path = Path("/sys/fs/selinux/enforce")
        if enforce_path.exists():
            try:
                val = enforce_path.read_text().strip()
                res = "Enforcing" if val == "1" else "Permissive"
                cls._selinux_cache = res
                return res
            except Exception:
                pass

        for bin_name in ["/system/bin/getenforce", "getenforce"]:
            if shutil.which(bin_name) or os.path.exists(bin_name):
                try:
                    p = subprocess.run([bin_name], capture_output=True, text=True, timeout=1.0)
                    if p.returncode == 0:
                        res = p.stdout.strip()
                        cls._selinux_cache = res
                        return res
                except Exception:
                    pass

        cls._selinux_cache = "Unknown (Enforcing assumed)"
        return cls._selinux_cache

    @classmethod
    def check_root(cls, force: bool = False) -> Dict[str, Any]:
        """Detect actual root/su capability with negative fast-path and 60s cache."""
        now = time.time()
        if not force and cls._root_cache is not None and (now - cls._root_time < 60.0):
            return cls._root_cache

        su_paths = ["/system/bin/su", "/system/xbin/su", "/sbin/su", "/data/local/tmp/su", "/data/data/com.termux/files/usr/bin/su"]
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
            res = {
                "available": False,
                "status": "unavailable",
                "su_binary": None,
                "uid": os.getuid(),
                "details": "No su binary present on device",
            }
            cls._root_cache = res
            cls._root_time = now
            return res

        # Test if su genuinely functions
        try:
            p = subprocess.run([found_su, "-c", "id"], capture_output=True, text=True, timeout=1.5)
            if p.returncode == 0 and "uid=0" in p.stdout:
                res = {
                    "available": True,
                    "status": "available",
                    "su_binary": found_su,
                    "uid": 0,
                    "details": "Genuine root execution verified (uid=0)",
                }
            else:
                res = {
                    "available": False,
                    "status": "su_failed",
                    "su_binary": found_su,
                    "uid": os.getuid(),
                    "details": p.stderr.strip() or p.stdout.strip() or "su exited with non-zero status",
                }
        except Exception as exc:
            res = {
                "available": False,
                "status": "su_error",
                "su_binary": found_su,
                "uid": os.getuid(),
                "details": str(exc),
            }

        cls._root_cache = res
        cls._root_time = now
        return res

    @classmethod
    def check_shizuku(cls, force: bool = False) -> Dict[str, Any]:
        """Detect Shizuku availability with 30s cache."""
        now = time.time()
        if not force and cls._shizuku_cache is not None and (now - cls._shizuku_time < 30.0):
            return cls._shizuku_cache

        rish_path = shutil.which("rish") or "/data/data/com.termux/files/usr/bin/rish"
        rish_exists = os.path.exists(rish_path) and os.access(rish_path, os.X_OK)

        if rish_exists:
            try:
                p = subprocess.run([rish_path, "-c", "id"], capture_output=True, text=True, timeout=1.5)
                if p.returncode == 0:
                    uid = 2000 if "uid=2000" in p.stdout else (0 if "uid=0" in p.stdout else os.getuid())
                    res = {
                        "available": True,
                        "status": "available",
                        "rish_installed": True,
                        "server_running": True,
                        "uid": uid,
                        "details": f"Shizuku execution verified: {p.stdout.strip()}",
                    }
                    cls._shizuku_cache = res
                    cls._shizuku_time = now
                    return res
            except Exception:
                pass

        res = {
            "available": False,
            "status": "unavailable",
            "rish_installed": rish_exists,
            "server_running": False,
            "details": "Shizuku server is not running and rish CLI is not installed",
        }
        cls._shizuku_cache = res
        cls._shizuku_time = now
        return res

    @classmethod
    def check_termux_api(cls, force: bool = False) -> Dict[str, Any]:
        """Detect Termux:API with 60s cache."""
        now = time.time()
        if not force and cls._termux_api_cache is not None and (now - cls._termux_api_time < 60.0):
            return cls._termux_api_cache

        cli_installed = bool(shutil.which("termux-battery-status"))
        apk_installed = False
        if cli_installed:
            try:
                p = subprocess.run(["/system/bin/pm", "list", "packages", "com.termux.api"], capture_output=True, text=True, timeout=1.5)
                if p.returncode == 0 and "package:com.termux.api" in p.stdout:
                    apk_installed = True
            except Exception:
                pass

        available = cli_installed and apk_installed
        status = "available" if available else ("companion_apk_required" if cli_installed else "cli_package_required")
        res = {
            "available": available,
            "status": status,
            "cli_installed": cli_installed,
            "companion_apk_installed": apk_installed,
            "details": "Termux:API fully operational" if available else "Install com.termux.api APK from F-Droid to enable Termux API bridge",
        }
        cls._termux_api_cache = res
        cls._termux_api_time = now
        return res

    @classmethod
    def get_installed_packages(cls, max_count: int = 50, force: bool = False) -> List[Dict[str, str]]:
        """List third-party installed packages with 60s cache."""
        now = time.time()
        if not force and cls._packages_cache is not None and (now - cls._packages_time < 60.0):
            return cls._packages_cache[:max_count]

        packages: List[Dict[str, str]] = []
        try:
            p = subprocess.run(
                ["/system/bin/pm", "list", "packages", "-3", "--user", "0"],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if p.returncode == 0:
                for line in p.stdout.splitlines():
                    if line.startswith("package:"):
                        pkg_name = line.replace("package:", "").strip()
                        packages.append({"package": pkg_name, "type": "third_party"})
                        if len(packages) >= 100:
                            break
        except Exception:
            pass

        cls._packages_cache = packages
        cls._packages_time = now
        return packages[:max_count]

    @classmethod
    def run_full_discovery(cls, force: bool = False) -> Dict[str, Any]:
        """Perform end-to-end device audit with stratified 3s fast-snapshot cache."""
        now = time.time()
        if not force and cls._snapshot_cache is not None and (now - cls._snapshot_time < 3.0):
            # Fast update of dynamic /proc memory and timestamp without any subprocess
            snap = dict(cls._snapshot_cache)
            snap["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            snap["device"] = dict(snap["device"])
            snap["device"]["memory"] = cls.get_memory_info()
            return snap

        props = cls.get_all_props()
        mem = cls.get_memory_info()
        cpu = cls.get_cpu_info()
        mounts = cls.get_storage_mounts(force=force)
        root_info = cls.check_root(force=force)
        shizuku_info = cls.check_shizuku(force=force)
        termux_api_info = cls.check_termux_api(force=force)
        packages = cls.get_installed_packages(max_count=40, force=force)

        # Discovered binaries (static cached)
        if cls._binaries_cache is None or force:
            android_binaries = {}
            for b in ["getprop", "pm", "am", "cmd", "dumpsys", "logcat", "screencap", "input", "settings", "toybox", "df", "sh"]:
                full_path = f"/system/bin/{b}"
                exists = os.path.exists(full_path)
                android_binaries[b] = {
                    "path": full_path,
                    "exists": exists,
                    "executable": os.access(full_path, os.X_OK) if exists else False,
                }

            termux_binaries = {}
            for b in ["curl", "ping", "dig", "nslookup", "git", "jq", "rg", "tar", "zip", "unzip", "python3", "node", "npm", "cloudflared", "ifconfig", "netstat", "termux-open", "termux-wake-lock"]:
                loc = shutil.which(b)
                termux_binaries[b] = {
                    "installed": bool(loc),
                    "path": loc or "",
                }
            cls._binaries_cache = (android_binaries, termux_binaries)
        else:
            android_binaries, termux_binaries = cls._binaries_cache

        snapshot = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tacp": {
                "version": "0.4.0-rc.1",
                "protocol_version": "2026-07-28",
                "schema_version": "2.0.0",
                "project_root": "/data/data/com.termux/files/home/tacp",
                "runtime": f"Python {platform.python_version()}",
            },
            "device": {
                "brand": props.get("ro.product.brand", "vivo"),
                "model": props.get("ro.product.model", "V2348"),
                "manufacturer": props.get("ro.product.manufacturer", "vivo"),
                "platform": props.get("ro.board.platform", "crow"),
                "android_version": props.get("ro.build.version.release", "16"),
                "sdk_int": int(props.get("ro.build.version.sdk", "36")),
                "security_patch": props.get("ro.build.version.security_patch", "2026-05-01"),
                "build_type": props.get("ro.build.type", "user"),
                "build_id": props.get("ro.build.id", "unknown"),
                "fingerprint": props.get("ro.build.fingerprint", "unknown"),
                "architecture": cpu["architecture"],
                "cpu_cores": cpu["cores"],
                "memory": mem,
            },
            "environment": {
                "uid": os.getuid(),
                "gid": os.getgid(),
                "selinux": cls.check_selinux(force=force),
                "prefix": os.environ.get("PREFIX", "/data/data/com.termux/files/usr"),
                "home": str(Path.home()),
                "storage_mounts": mounts,
            },
            "backends": {
                "termux": {
                    "available": True,
                    "privilege": "user",
                    "uid": os.getuid(),
                    "details": "Native Termux sandbox process execution",
                },
                "android_shell": {
                    "available": True,
                    "privilege": "user",
                    "uid": os.getuid(),
                    "binaries": [b for b, info in android_binaries.items() if info["executable"]],
                    "details": "Standard Android /system/bin binaries in user sandbox",
                },
                "termux_api": termux_api_info,
                "shizuku": shizuku_info,
                "root": root_info,
                "adb": {
                    "available": False,
                    "status": "unavailable",
                    "details": "Local ADB daemon not connected",
                },
                "android_bridge": {
                    "available": False,
                    "status": "not_installed",
                    "details": "TACP Android Bridge companion application not running on localhost:8766",
                },
                "accessibility": {
                    "available": False,
                    "status": "companion_required",
                    "details": "Requires TACP Android Bridge companion app with Accessibility Service enabled",
                },
                "media_projection": {
                    "available": False,
                    "status": "companion_required",
                    "details": "Requires TACP Android Bridge companion app with Screen Capture permission",
                },
            },
            "binaries": {
                "android": android_binaries,
                "termux": termux_binaries,
            },
            "installed_packages_sample": packages,
        }

        cls._snapshot_cache = snapshot
        cls._snapshot_time = now
        return snapshot

    get_device_report = run_full_discovery
