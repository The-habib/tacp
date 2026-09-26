"""Stratified, high-performance DeviceState cache and orchestration engine for Android."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class StateField:
    value: Any
    updated_at: str
    timestamp: float
    age_ms: float
    source: str
    freshness: str  # "fresh" | "cached" | "stale"
    confidence: str  # "verified" | "probed" | "fallback"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "updated_at": self.updated_at,
            "age_ms": round(self.age_ms, 2),
            "source": self.source,
            "freshness": self.freshness,
            "confidence": self.confidence,
        }


class DeviceStateManager:
    """Central state manager providing coherent, stratified, and non-blocking device status."""

    _instance: Optional[DeviceStateManager] = None

    # Formal TTL tiers per CACHE-CONSISTENCY specification
    TTL_SELINUX = 86400.0 * 365  # Permanent
    TTL_BATTERY = 15.0  # 15s
    TTL_NETWORK = 5.0  # 5s
    TTL_PACKAGES = 300.0  # 300s (5 minutes)
    TTL_COMPANION = 10.0  # 10s
    TTL_MEMORY = 3.0  # 3s
    TTL_STORAGE = 30.0  # 30s
    TTL_PROCESSES = 2.0  # 2s
    TTL_AUDIO = 30.0  # 30s
    TTL_SCREEN = 10.0  # 10s

    STATIC_TTL = 86400.0
    SLOW_TTL = 60.0
    FAST_TTL = 3.0

    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def get_default(cls) -> DeviceStateManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def invalidate(self, key: Optional[str] = None) -> None:
        """Invalidate a specific cached field or clear the entire state cache."""
        if key is not None:
            self._cache.pop(key, None)
        else:
            self._cache.clear()

    def get_field(self, key: str) -> Optional[StateField]:
        """Retrieve a field from cache, returning safe stale data if present."""
        entry = self._cache.get(key)
        if not entry:
            return None
        now = time.time()
        age = now - entry["timestamp"]
        return StateField(
            value=entry["value"],
            updated_at=entry["updated_at"],
            timestamp=entry["timestamp"],
            age_ms=age * 1000.0,
            source=entry["source"],
            freshness="fresh" if age < 0.05 else ("cached" if age <= self.FAST_TTL else "stale"),
            confidence=entry["confidence"],
        )

    def _get_cached_field(self, key: str, max_age: float) -> Optional[StateField]:
        entry = self._cache.get(key)
        if not entry:
            return None
        now = time.time()
        age = now - entry["timestamp"]
        if age <= max_age:
            return StateField(
                value=entry["value"],
                updated_at=entry["updated_at"],
                timestamp=entry["timestamp"],
                age_ms=age * 1000.0,
                source=entry["source"],
                freshness="cached" if age > 0.05 else "fresh",
                confidence=entry["confidence"],
            )
        return None

    def _get_stale_fallback(
        self, key: str, fallback_value: Any, fallback_source: str
    ) -> StateField:
        """Return stale cached entry if available, otherwise return safe fallback and store negative cache."""
        entry = self._cache.get(key)
        now = time.time()
        if entry:
            age = now - entry["timestamp"]
            return StateField(
                value=entry["value"],
                updated_at=entry["updated_at"],
                timestamp=entry["timestamp"],
                age_ms=age * 1000.0,
                source=entry["source"],
                freshness="stale",
                confidence="fallback",
            )
        now_str = datetime.now(timezone.utc).isoformat()
        # Store negative cache to prevent stampede of failing probes
        self._cache[key] = {
            "value": fallback_value,
            "updated_at": now_str,
            "timestamp": now,
            "source": fallback_source,
            "confidence": "fallback",
        }
        return StateField(
            value=fallback_value,
            updated_at=now_str,
            timestamp=now,
            age_ms=0.0,
            source=fallback_source,
            freshness="stale",
            confidence="fallback",
        )

    def _store_field(
        self, key: str, value: Any, source: str, confidence: str = "verified"
    ) -> StateField:
        now = time.time()
        now_str = datetime.now(timezone.utc).isoformat()
        self._cache[key] = {
            "value": value,
            "updated_at": now_str,
            "timestamp": now,
            "source": source,
            "confidence": confidence,
        }
        return StateField(
            value=value,
            updated_at=now_str,
            timestamp=now,
            age_ms=0.0,
            source=source,
            freshness="fresh",
            confidence=confidence,
        )

    # 1. SELinux (PERMANENT)
    def get_selinux(self, force: bool = False) -> StateField:
        if not force:
            cached = self._get_cached_field("selinux", self.TTL_SELINUX)
            if cached:
                return cached
        try:
            enforce_path = Path("/sys/fs/selinux/enforce")
            if enforce_path.exists():
                try:
                    val = enforce_path.read_text().strip()
                    status = "Enforcing" if val == "1" else "Permissive"
                    return self._store_field(
                        "selinux", status, source="/sys/fs/selinux/enforce", confidence="verified"
                    )
                except Exception:
                    pass
            from tacp.core.discovery import DeviceDiscovery

            status = DeviceDiscovery.check_selinux()
            return self._store_field(
                "selinux", status, source="DeviceDiscovery.check_selinux", confidence="verified"
            )
        except Exception:
            return self._get_stale_fallback("selinux", "Permissive", "fallback.default")

    # 2. Battery (15s TTL)
    def get_battery(self, force: bool = False) -> StateField:
        if not force:
            cached = self._get_cached_field("battery", self.TTL_BATTERY)
            if cached:
                return cached
        val: Dict[str, Any] = {
            "percentage": 100,
            "status": "unknown",
            "plugged": "unknown",
            "temperature": 0.0,
        }
        source = "sysfs"
        sys_batt = Path("/sys/class/power_supply/battery")
        try:
            if sys_batt.exists():
                cap = (sys_batt / "capacity").read_text().strip()
                val["percentage"] = int(cap)
                st = (sys_batt / "status").read_text().strip()
                val["status"] = st.lower()
                temp = (sys_batt / "temp").read_text().strip()
                val["temperature"] = int(temp) / 10.0
                return self._store_field("battery", val, source=source, confidence="probed")
            elif shutil.which("termux-battery-status"):
                p = subprocess.run(
                    ["termux-battery-status"], capture_output=True, text=True, timeout=1.0
                )
                if p.returncode == 0:
                    val = json.loads(p.stdout)
                    return self._store_field(
                        "battery", val, source="termux_api", confidence="probed"
                    )
        except Exception:
            pass
        return self._get_stale_fallback("battery", val, "fallback.battery")

    # 3. Network (5s TTL)
    def get_network(self, force: bool = False) -> StateField:
        if not force:
            cached = self._get_cached_field("network", self.TTL_NETWORK)
            if cached:
                return cached
        interfaces = []
        try:
            with open("/proc/net/dev", "r") as f:
                for line in f.readlines()[2:]:
                    parts = line.split(":")
                    if len(parts) == 2:
                        interfaces.append(parts[0].strip())
        except Exception:
            pass

        if not interfaces:
            # Fallback to ifconfig
            try:
                p = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=1.0)
                for line in p.stdout.splitlines():
                    if ": flags=" in line:
                        interfaces.append(line.split(":")[0].strip())
            except Exception:
                pass

        if interfaces:
            val = {
                "interfaces": interfaces,
                "count": len(interfaces),
                "has_connectivity": any(i != "lo" for i in interfaces),
            }
            return self._store_field("network", val, source="ifconfig", confidence="verified")
        return self._get_stale_fallback(
            "network",
            {"interfaces": ["lo"], "count": 1, "has_connectivity": False},
            "fallback.offline",
        )

    # 4. Packages (300s TTL)
    def get_packages(self, force: bool = False) -> StateField:
        if not force:
            cached = self._get_cached_field("packages", self.TTL_PACKAGES)
            if cached:
                return cached
        try:
            p = subprocess.run(
                ["pm", "list", "packages"], capture_output=True, text=True, timeout=3.0
            )
            if p.returncode == 0:
                pkgs = [
                    line.replace("package:", "").strip()
                    for line in p.stdout.splitlines()
                    if line.startswith("package:")
                ]
                val = {"total_count": len(pkgs), "sample": pkgs[:10]}
                return self._store_field(
                    "packages", val, source="android.pm", confidence="verified"
                )
        except Exception:
            pass
        return self._get_stale_fallback(
            "packages", {"total_count": 0, "sample": []}, "fallback.packages"
        )

    # 5. Companion (10s TTL)
    def get_companion(self, force: bool = False) -> StateField:
        if not force:
            cached = self._get_cached_field("companion", self.TTL_COMPANION)
            if cached:
                return cached
        try:
            from tacp.core.discovery import DeviceDiscovery

            val = DeviceDiscovery.check_termux_api()
            return self._store_field(
                "companion", val, source="companion.probe", confidence="probed"
            )
        except Exception:
            return self._get_stale_fallback(
                "companion", {"status": "disconnected", "available": False}, "fallback.companion"
            )

    # 6. Memory (3s TTL)
    def get_memory(self, force: bool = False) -> StateField:
        if not force:
            cached = self._get_cached_field("memory", self.TTL_MEMORY)
            if cached:
                return cached
        try:
            from tacp.core.discovery import DeviceDiscovery

            val = DeviceDiscovery.get_memory_info()
            return self._store_field(
                "memory", val, source="linux.proc.meminfo", confidence="verified"
            )
        except Exception:
            return self._get_stale_fallback(
                "memory", {"total_mb": 0, "available_mb": 0}, "fallback.memory"
            )

    # 7. Storage (30s TTL)
    def get_storage(self, force: bool = False) -> StateField:
        if not force:
            cached = self._get_cached_field("storage", self.TTL_STORAGE)
            if cached:
                return cached
        try:
            from tacp.core.discovery import DeviceDiscovery

            mounts = DeviceDiscovery.get_storage_mounts()
            val = {
                "mount_count": len(mounts),
                "storage_roots": mounts,
            }
            return self._store_field("storage", val, source="posix.statvfs", confidence="verified")
        except Exception:
            return self._get_stale_fallback(
                "storage", {"mount_count": 0, "storage_roots": []}, "fallback.storage"
            )

    # 8. Processes (2s TTL)
    def get_processes(self, force: bool = False) -> StateField:
        if not force:
            cached = self._get_cached_field("processes", self.TTL_PROCESSES)
            if cached:
                return cached
        count = 0
        try:
            for item in os.listdir("/proc"):
                if item.isdigit():
                    count += 1
            val = {
                "total_processes": count,
                "accessible_scope": "procfs_pid_scan",
            }
            return self._store_field(
                "processes", val, source="linux.proc.pids", confidence="verified"
            )
        except Exception:
            return self._get_stale_fallback(
                "processes", {"total_processes": 1, "accessible_scope": "fallback"}, "fallback.proc"
            )

    # 9. Audio (30s TTL)
    def get_audio(self, force: bool = False) -> StateField:
        if not force:
            cached = self._get_cached_field("audio", self.TTL_AUDIO)
            if cached:
                return cached
        val = {"status": "idle", "streams": {"music": 0, "notification": 0}}
        if shutil.which("termux-volume"):
            try:
                p = subprocess.run(["termux-volume"], capture_output=True, text=True, timeout=1.0)
                if p.returncode == 0:
                    val = {"status": "active", "streams": json.loads(p.stdout)}
                    return self._store_field(
                        "audio", val, source="termux-volume", confidence="probed"
                    )
            except Exception:
                pass
        return self._store_field("audio", val, source="audio.fallback", confidence="fallback")

    # 10. Screen (10s TTL)
    def get_screen(self, force: bool = False) -> StateField:
        if not force:
            cached = self._get_cached_field("screen", self.TTL_SCREEN)
            if cached:
                return cached
        val = {"screen_on": True, "width": 1080, "height": 2400, "density": 440}
        source = "companion.screen"
        try:
            from tacp.backends.companion_transport import HttpCompanionTransport

            transport = HttpCompanionTransport()
            if transport.is_connected():
                res = transport.send_request("/screen/info", timeout=0.5)
                if res.get("status") == "ok":
                    val = res.get("data", val)
                    return self._store_field("screen", val, source=source, confidence="verified")
        except Exception:
            pass
        return self._store_field("screen", val, source="screen.default_spec", confidence="probed")

    # Identity (STATIC)
    def get_identity(self, force: bool = False) -> StateField:
        if not force:
            cached = self._get_cached_field("identity", self.STATIC_TTL)
            if cached:
                return cached
        from tacp.core.discovery import DeviceDiscovery

        props = DeviceDiscovery.get_all_props()
        val = {
            "brand": props.get("ro.product.brand", "vivo"),
            "model": props.get("ro.product.model", "V2348"),
            "manufacturer": props.get("ro.product.manufacturer", "vivo"),
            "device": props.get("ro.product.device", "crow"),
            "build_id": props.get("ro.build.id", "unknown"),
        }
        return self._store_field(
            "identity", val, source="android.os.SystemProperties", confidence="verified"
        )

    # Runtime (STATIC)
    def get_runtime(self, force: bool = False) -> StateField:
        if not force:
            cached = self._get_cached_field("runtime", self.STATIC_TTL)
            if cached:
                return cached
        from tacp.core.discovery import DeviceDiscovery

        props = DeviceDiscovery.get_all_props()
        cpu = DeviceDiscovery.get_cpu_info()
        val = {
            "os": "Android",
            "android_version": props.get("ro.build.version.release", "16"),
            "sdk_int": int(props.get("ro.build.version.sdk", "36")),
            "security_patch": props.get("ro.build.version.security_patch", "unknown"),
            "architecture": cpu["architecture"],
            "kernel": platform.release(),
            "python_version": platform.python_version(),
            "cpu_cores": cpu["cores"],
            "selinux": self.get_selinux(force).value,
        }
        return self._store_field("runtime", val, source="linux.proc.cpuinfo", confidence="verified")

    # Capabilities (SLOW)
    def get_capabilities(self, force: bool = False) -> StateField:
        if not force:
            cached = self._get_cached_field("capabilities", self.SLOW_TTL)
            if cached:
                return cached
        from tacp.engine.registry import default_registry

        caps = default_registry.list_capabilities()
        val = {
            "total_count": len(caps),
            "available_count": sum(1 for c in caps if c.get("availability") == "available"),
            "companion_count": sum(1 for c in caps if "companion" in str(c.get("availability"))),
            "privileged_count": sum(
                1
                for c in caps
                if "root" in str(c.get("availability")) or "shizuku" in str(c.get("availability"))
            ),
        }
        return self._store_field(
            "capabilities", val, source="tacp.engine.registry", confidence="verified"
        )

    # Providers / Backends (SLOW)
    def get_providers(self, force: bool = False) -> StateField:
        if not force:
            cached = self._get_cached_field("providers", self.SLOW_TTL)
            if cached:
                return cached
        from tacp.backends.manager import BackendManager

        bm = BackendManager.get_default()
        backends = bm.probe_all(force=force)
        val = {b: info.get("status") for b, info in backends.items()}
        return self._store_field(
            "providers", val, source="tacp.backends.manager", confidence="verified"
        )

    # Complete DeviceState Snapshot (All 10 fields + identity/runtime/providers)
    def get_state_snapshot(self, force: bool = False) -> Dict[str, Any]:
        """Aggregate stratified DeviceState with per-field timestamps, sources, and freshness.

        Protected by SingleFlight coalescing to prevent stampedes when multiple concurrent
        callers request expensive hardware refresh simultaneously.
        """
        if force:
            from tacp.core.coalesce import get_singleflight_group

            return get_singleflight_group().do(
                "state_snapshot_force", self._build_state_snapshot, True
            )
        return self._build_state_snapshot(False)

    def _build_state_snapshot(self, force: bool) -> Dict[str, Any]:
        return {
            "identity": self.get_identity(force).to_dict(),
            "runtime": self.get_runtime(force).to_dict(),
            "selinux": self.get_selinux(force).to_dict(),
            "battery": self.get_battery(force).to_dict(),
            "memory": self.get_memory(force).to_dict(),
            "storage": self.get_storage(force).to_dict(),
            "network": self.get_network(force).to_dict(),
            "processes": self.get_processes(force).to_dict(),
            "packages": self.get_packages(force).to_dict(),
            "companion": self.get_companion(force).to_dict(),
            "audio": self.get_audio(force).to_dict(),
            "screen": self.get_screen(force).to_dict(),
            "capabilities": self.get_capabilities(force).to_dict(),
            "providers": self.get_providers(force).to_dict(),
        }
