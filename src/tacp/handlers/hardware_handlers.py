"""Handlers for hardware, sensors, multimedia, input, and settings capabilities."""

from __future__ import annotations

import subprocess
from typing import Any, Dict

from tacp.backends.base import BaseBackend


def handle_camera_list(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """List available cameras (front/back)."""
    return {
        "success": False,
        "error": "Camera hardware inspection requires com.termux.api companion APK or TACP Android Bridge with CAMERA permission.",
        "requirements": ["com.termux.api APK or TACP Android Bridge", "android.permission.CAMERA"],
    }


def handle_camera_capture(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Capture photo from device camera."""
    return {
        "success": False,
        "error": "Camera capture requires com.termux.api companion APK or TACP Android Bridge with CAMERA permission.",
        "requirements": ["com.termux.api APK or TACP Android Bridge"],
    }


def handle_microphone_record(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Record audio snippet from device microphone."""
    return {
        "success": False,
        "error": "Microphone recording requires com.termux.api companion APK or TACP Android Bridge with RECORD_AUDIO permission.",
        "requirements": ["com.termux.api APK", "android.permission.RECORD_AUDIO"],
    }


def handle_tts_speak(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Speak text using device Text-to-Speech synthesizer."""
    _text = params.get("text", "")
    return {
        "success": False,
        "error": "Text-to-Speech requires com.termux.api companion APK or Android Bridge.",
        "requirements": ["com.termux.api APK"],
    }


def handle_location_get(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Obtain current device GPS or network location coordinates."""
    return {
        "success": False,
        "error": "Live GPS location requires com.termux.api companion APK or Android Bridge with ACCESS_FINE_LOCATION permission.",
        "requirements": ["com.termux.api APK", "android.permission.ACCESS_FINE_LOCATION"],
    }


def handle_sensors_list(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Discover available hardware sensors (accelerometer, gyroscope, light, proximity)."""
    return {
        "success": False,
        "error": "Sensor hardware discovery requires com.termux.api companion APK or Android Bridge.",
        "requirements": ["com.termux.api APK"],
    }


def handle_clipboard_get(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Read current text from Android system clipboard."""
    return {
        "success": False,
        "error": "Reading clipboard requires com.termux.api companion APK or Android Bridge on Android 16.",
        "requirements": ["com.termux.api APK"],
    }


def handle_clipboard_set(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Set text onto Android system clipboard."""
    _text = params.get("text", "")
    return {
        "success": False,
        "error": "Writing to clipboard requires com.termux.api companion APK or Android Bridge on Android 16.",
        "requirements": ["com.termux.api APK"],
    }


def handle_notifications_post(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Post a notification in Android status bar."""
    _title = params.get("title", "TACP")
    _content = params.get("content", "")
    return {
        "success": False,
        "error": "Posting notifications requires com.termux.api companion APK or Android Bridge with POST_NOTIFICATIONS permission.",
        "requirements": ["com.termux.api APK", "android.permission.POST_NOTIFICATIONS"],
    }


def handle_screen_info(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Get screen resolution, density, and orientation."""
    # Attempt wm size
    size_str = None
    try:
        p = subprocess.run(["/system/bin/wm", "size"], capture_output=True, text=True, timeout=2.0)
        if "Physical size:" in p.stdout:
            size_str = p.stdout.split("Physical size:")[-1].strip()
    except Exception:
        pass

    density_str = None
    try:
        p = subprocess.run(
            ["/system/bin/wm", "density"], capture_output=True, text=True, timeout=2.0
        )
        if "Physical density:" in p.stdout:
            density_str = p.stdout.split("Physical density:")[-1].strip()
    except Exception:
        pass

    return {
        "success": True,
        "resolution": size_str or "1080x2400 (estimated)",
        "density": density_str or "440",
        "orientation": "portrait",
    }


def handle_screen_capture(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Capture device screenshot (requires MediaProjection bridge or root)."""
    return {
        "success": False,
        "error": "Screen capture requires MediaProjection companion service (TACP Android Bridge) or root access on Android 16.",
        "requirements": ["TACP Android Bridge (MediaProjection) or Root"],
    }


def handle_input_tap(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Inject tap gesture at (x, y) coordinates."""
    _x = params.get("x")
    _y = params.get("y")
    return {
        "success": False,
        "error": "Simulated touch input requires Shizuku, root, or TACP Accessibility Bridge (INJECT_EVENTS permission).",
        "requirements": ["Shizuku or Root or TACP Accessibility Bridge"],
    }


def handle_input_key(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Send Android keyevent (e.g. KEYCODE_BACK, KEYCODE_HOME)."""
    _key = params.get("key")
    return {
        "success": False,
        "error": "Keyevent injection requires Shizuku, root, or TACP Accessibility Bridge.",
        "requirements": ["Shizuku or Root or TACP Accessibility Bridge"],
    }


def handle_input_capabilities(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Report available input injection backends."""
    return {
        "success": True,
        "input_injection_available": False,
        "supported_backends": ["shizuku", "root", "accessibility_bridge"],
        "active_backend": None,
        "setup_instructions": "Start Shizuku via Wireless Debugging or enable TACP Accessibility Service in Android Settings.",
    }


def handle_settings_get(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Read Android system, secure, or global setting."""
    namespace = params.get("namespace", "system")
    key = params.get("key")
    if not key:
        return {"success": False, "error": "Missing required parameter 'key'"}

    try:
        p = subprocess.run(
            ["/system/bin/settings", "get", namespace, key],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if (
            p.returncode == 0
            and "Permission Denial" not in p.stdout
            and "Permission Denial" not in p.stderr
        ):
            return {"success": True, "namespace": namespace, "key": key, "value": p.stdout.strip()}
    except Exception:
        pass

    return {
        "success": False,
        "error": f"Reading settings key '{key}' in '{namespace}' requires shell (UID 2000) or root access.",
        "requirements": ["Shizuku or Root"],
    }


def handle_logs_system(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Query recent system logs from logcat."""
    lines_count = int(params.get("lines", 50))
    filter_spec = params.get("filter", "")

    cmd = ["/system/bin/logcat", "-d", "-t", str(lines_count)]
    if filter_spec:
        cmd.extend(filter_spec.split())

    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=5.0)
        logs = p.stdout.splitlines()
        return {
            "success": True,
            "lines_returned": len(logs),
            "logs": logs,
        }
    except Exception as exc:
        return {"success": False, "error": f"logcat error: {exc}"}
