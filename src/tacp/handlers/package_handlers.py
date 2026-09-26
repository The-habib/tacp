"""Handlers for package.* and app.* namespace capabilities."""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from tacp.backends.base import BaseBackend


def handle_package_list(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """List installed Android packages."""
    pkg_type = params.get("type", "third_party")  # "third_party", "system", "all"
    user = params.get("user", "0")
    filter_query = params.get("filter", "").lower()
    limit = int(params.get("limit", 200))

    pm_cmd = ["/system/bin/pm", "list", "packages"]
    if pkg_type == "third_party":
        pm_cmd.append("-3")
    elif pkg_type == "system":
        pm_cmd.append("-s")

    if user is not None:
        pm_cmd.extend(["--user", str(user)])

    packages: List[str] = []
    try:
        p = subprocess.run(pm_cmd, capture_output=True, text=True, timeout=5.0)
        if p.returncode == 0:
            for line in p.stdout.splitlines():
                if line.startswith("package:"):
                    name = line.replace("package:", "").strip()
                    if not filter_query or filter_query in name.lower():
                        packages.append(name)
                        if len(packages) >= limit:
                            break
    except Exception as exc:
        return {"success": False, "error": f"pm command failed: {exc}"}

    return {
        "success": True,
        "type": pkg_type,
        "count": len(packages),
        "packages": packages,
    }


def handle_package_path(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Get APK file path for an installed package."""
    pkg = params.get("package")
    if not pkg:
        return {"success": False, "error": "Missing required parameter 'package'"}

    try:
        p = subprocess.run(["/system/bin/pm", "path", pkg], capture_output=True, text=True, timeout=3.0)
        if p.returncode == 0 and "package:" in p.stdout:
            paths = []
            for line in p.stdout.splitlines():
                if line.startswith("package:"):
                    paths.append(line.replace("package:", "").strip())
            return {"success": True, "package": pkg, "paths": paths, "primary_apk": paths[0] if paths else None}
        return {"success": False, "error": f"Package '{pkg}' not found"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def handle_package_info(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Inspect package metadata directly from its installed APK."""
    pkg = params.get("package")
    if not pkg:
        return {"success": False, "error": "Missing required parameter 'package'"}

    path_res = handle_package_path(backend, {"package": pkg})
    if not path_res.get("success") or not path_res.get("primary_apk"):
        return {"success": False, "error": f"Could not locate APK for package '{pkg}'"}

    apk_path = Path(path_res["primary_apk"])
    if not apk_path.exists():
        return {"success": False, "error": f"APK path does not exist: {apk_path}"}

    info: Dict[str, Any] = {
        "package": pkg,
        "apk_path": str(apk_path),
        "size_bytes": apk_path.stat().st_size,
        "size_mb": round(apk_path.stat().st_size / (1024 * 1024), 2),
    }

    try:
        with zipfile.ZipFile(apk_path) as z:
            names = z.namelist()
            info["has_manifest"] = "AndroidManifest.xml" in names
            info["has_resources"] = "resources.arsc" in names
            info["dex_count"] = sum(1 for n in names if n.endswith(".dex"))
            info["total_files"] = len(names)
    except Exception as exc:
        info["zip_error"] = str(exc)

    return {"success": True, "info": info}


def handle_app_launch(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Launch an Android application by package name."""
    pkg = params.get("package")
    if not pkg:
        return {"success": False, "error": "Missing required parameter 'package'"}

    # 1. Attempt monkey launcher trick
    env = os.environ.copy()
    env["PATH"] = "/system/bin:" + env.get("PATH", "")
    try:
        p = subprocess.run(
            ["/system/bin/monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"],
            env=env,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if "Events injected: 1" in p.stdout or p.returncode == 0:
            return {"success": True, "package": pkg, "method": "monkey_launcher", "message": f"Application {pkg} launched successfully"}
    except Exception:
        pass

    # 2. Attempt termux-am
    termux_am = shutil.which("termux-am")
    if termux_am:
        try:
            p = subprocess.run([termux_am, "start", "-n", pkg], capture_output=True, text=True, timeout=3.0)
            if p.returncode == 0:
                return {"success": True, "package": pkg, "method": "termux-am"}
        except Exception:
            pass

    return {
        "success": False,
        "error": f"Failed to launch {pkg}. May require Shizuku or Accessibility companion on Android 16.",
    }


def handle_app_open_url(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Open URL in default browser or handling application."""
    url = params.get("url")
    if not url:
        return {"success": False, "error": "Missing required parameter 'url'"}

    # Use termux-open-url
    open_bin = shutil.which("termux-open-url") or shutil.which("termux-open")
    if open_bin:
        try:
            p = subprocess.run([open_bin, url], capture_output=True, text=True, timeout=3.0)
            return {"success": p.returncode == 0, "url": url}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    return {"success": False, "error": "termux-open-url utility not found"}


def handle_package_install(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Install APK package (requires Shizuku or root)."""
    try:
        from tacp.core.state import DeviceStateManager
        DeviceStateManager.get_default().invalidate("packages")
    except Exception:
        pass
    apk_path = params.get("apk_path")
    if not apk_path:
        return {"success": False, "error": "Missing required parameter 'apk_path'"}

    # Check Shizuku / Root
    return {
        "success": False,
        "error": "Package installation requires Shizuku or root backend to grant INSTALL_PACKAGES permission on Android 16.",
        "requirements": ["Shizuku or Root"],
    }


def handle_package_uninstall(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Uninstall package (requires Shizuku or root)."""
    try:
        from tacp.core.state import DeviceStateManager
        DeviceStateManager.get_default().invalidate("packages")
    except Exception:
        pass
    pkg = params.get("package")
    return {
        "success": False,
        "error": f"Uninstalling package '{pkg}' requires Shizuku or root backend on Android 16.",
        "requirements": ["Shizuku or Root"],
    }
