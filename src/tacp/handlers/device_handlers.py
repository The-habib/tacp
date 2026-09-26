"""Handlers for device.* namespace capabilities."""

from __future__ import annotations

import os
import platform
import subprocess
import time
from typing import Any, Dict

from tacp.backends.base import BaseBackend
from tacp.core.discovery import DeviceDiscovery


def handle_device_info(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Return comprehensive hardware, Android OS, and environment info."""
    props = DeviceDiscovery.get_all_props()
    mem = DeviceDiscovery.get_memory_info()
    cpu = DeviceDiscovery.get_cpu_info()

    return {
        "success": True,
        "device": {
            "brand": props.get("ro.product.brand", "Android"),
            "model": props.get("ro.product.model", "Generic"),
            "manufacturer": props.get("ro.product.manufacturer", "Android"),
            "platform": props.get("ro.board.platform", "unknown"),
            "hardware": props.get("ro.hardware", cpu.get("hardware", "")),
        },
        "os": {
            "android_version": props.get("ro.build.version.release", "16"),
            "sdk_int": int(props.get("ro.build.version.sdk", "36")),
            "security_patch": props.get("ro.build.version.security_patch", "unknown"),
            "build_type": props.get("ro.build.type", "user"),
            "build_id": props.get("ro.build.id", "unknown"),
            "fingerprint": props.get("ro.build.fingerprint", "unknown"),
            "kernel": platform.release(),
        },
        "hardware": {
            "architecture": cpu.get("architecture", "aarch64"),
            "cpu_cores": cpu.get("cores", 8),
            "memory_total_mb": mem.get("total_mb", 0),
            "memory_available_mb": mem.get("available_mb", 0),
        },
        "environment": {
            "selinux": DeviceDiscovery.check_selinux(),
            "uid": os.getuid(),
            "gid": os.getgid(),
        },
    }


def handle_device_properties(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Query specific or all Android getprop system properties."""
    key = params.get("key")
    if key:
        val = DeviceDiscovery.get_prop(key)
        return {"success": True, "key": key, "value": val}

    props = DeviceDiscovery.get_all_props()
    return {"success": True, "count": len(props), "properties": props}


def handle_device_battery(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Query device battery and power supply telemetry."""
    # 1. Try dumpsys battery
    try:
        p = subprocess.run(["/system/bin/dumpsys", "battery"], capture_output=True, text=True, timeout=2.0)
        if p.returncode == 0 and "level:" in p.stdout:
            data = {}
            for line in p.stdout.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    data[k.strip().lower()] = v.strip()
            level = int(data.get("level", 0)) if data.get("level", "").isdigit() else None
            return {
                "success": True,
                "percentage": level,
                "status": "charging" if data.get("status") in ("2", "charging") else "discharging",
                "health": data.get("health", "good"),
                "temperature_c": round(int(data.get("temperature", 0)) / 10.0, 1) if data.get("temperature", "").isdigit() else None,
                "source": "dumpsys",
            }
    except Exception:
        pass

    # 2. Return fallback notification of requirement
    return {
        "success": True,
        "percentage": None,
        "status": "active_on_battery",
        "details": "Direct battery read requires com.termux.api APK companion or Shizuku/root permissions on Android 16.",
        "requirements": ["com.termux.api APK"],
    }


def handle_device_uptime(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Return device uptime."""
    uptime_sec = 0.0
    uptime_file = "/proc/uptime"
    if os.path.exists(uptime_file):
        try:
            with open(uptime_file) as f:
                uptime_sec = float(f.read().split()[0])
        except Exception:
            pass

    hours = int(uptime_sec // 3600)
    minutes = int((uptime_sec % 3600) // 60)
    seconds = int(uptime_sec % 60)

    return {
        "success": True,
        "uptime_seconds": round(uptime_sec, 2),
        "formatted": f"{hours}h {minutes}m {seconds}s",
    }


def handle_device_snapshot(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Collect a complete multi-domain device state snapshot."""
    discovery = DeviceDiscovery.run_full_discovery()
    return {
        "success": True,
        "snapshot": discovery,
    }
