"""Handlers for storage.* namespace capabilities."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List

from tacp.backends.base import BaseBackend
from tacp.core.discovery import DeviceDiscovery


def handle_storage_overview(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Provide disk space metrics across all discovered storage roots."""
    mounts = DeviceDiscovery.get_storage_mounts()
    return {
        "success": True,
        "mount_count": len(mounts),
        "storage_roots": mounts,
    }


def handle_storage_mounts(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Parse and return mounted filesystems from /proc/mounts."""
    mounts_path = Path("/proc/mounts")
    if not mounts_path.exists():
        return {"success": False, "error": "/proc/mounts not available"}

    filter_type = params.get("filter_type", "")
    results: List[Dict[str, str]] = []
    try:
        for line in mounts_path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 3:
                device, mount_point, fs_type = parts[0], parts[1], parts[2]
                if filter_type and filter_type not in fs_type:
                    continue
                results.append({
                    "device": device,
                    "mount_point": mount_point,
                    "fs_type": fs_type,
                    "options": parts[3] if len(parts) > 3 else "",
                })
    except Exception as exc:
        return {"success": False, "error": f"Failed reading mounts: {exc}"}

    return {"success": True, "count": len(results), "mounts": results}


def handle_storage_large_files(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Find files larger than a given threshold (default: 50MB)."""
    root_str = params.get("path", "/data/data/com.termux/files/home")
    threshold_mb = float(params.get("threshold_mb", 50.0))
    threshold_bytes = int(threshold_mb * 1024 * 1024)
    limit = int(params.get("limit", 50))

    root = Path(root_str).expanduser().resolve()
    if not root.exists():
        return {"success": False, "error": f"Path not found: {root_str}"}

    large_files: List[Dict[str, Any]] = []
    for r, _, files in os.walk(root):
        for f in files:
            full = Path(r) / f
            try:
                if not full.is_symlink():
                    size = full.stat().st_size
                    if size >= threshold_bytes:
                        large_files.append({
                            "path": str(full),
                            "name": f,
                            "size_mb": round(size / (1024 * 1024), 2),
                            "size_bytes": size,
                        })
            except Exception:
                pass
        if len(large_files) >= limit:
            break

    large_files.sort(key=lambda x: x["size_bytes"], reverse=True)
    return {
        "success": True,
        "search_path": str(root),
        "threshold_mb": threshold_mb,
        "count": len(large_files),
        "files": large_files[:limit],
    }


def handle_storage_duplicates(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Find potential duplicate files based on size and SHA-256 hash."""
    root_str = params.get("path", "/data/data/com.termux/files/home")
    root = Path(root_str).expanduser().resolve()
    if not root.exists():
        return {"success": False, "error": f"Path not found: {root_str}"}

    size_map: Dict[int, List[Path]] = {}
    limit = int(params.get("limit", 20))

    for r, _, files in os.walk(root):
        for f in files:
            full = Path(r) / f
            try:
                if full.is_file() and not full.is_symlink():
                    sz = full.stat().st_size
                    if sz > 1024:  # Ignore tiny files (<1KB)
                        size_map.setdefault(sz, []).append(full)
            except Exception:
                pass

    duplicates: List[Dict[str, Any]] = []
    for sz, paths in size_map.items():
        if len(paths) > 1:
            hashes: Dict[str, List[str]] = {}
            for p in paths:
                try:
                    h = hashlib.sha256()
                    with open(p, "rb") as fp:
                        h.update(fp.read(512 * 1024))  # Sample first 512KB
                    digest = h.hexdigest()
                    hashes.setdefault(digest, []).append(str(p))
                except Exception:
                    pass
            for digest, match_list in hashes.items():
                if len(match_list) > 1:
                    duplicates.append({
                        "size_bytes": sz,
                        "size_mb": round(sz / (1024 * 1024), 3),
                        "hash_sample": digest[:16],
                        "paths": match_list,
                    })
                    if len(duplicates) >= limit:
                        break
        if len(duplicates) >= limit:
            break

    return {
        "success": True,
        "search_path": str(root),
        "duplicate_groups_found": len(duplicates),
        "duplicates": duplicates,
    }


def handle_storage_cleanup_candidates(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Identify temp, cache, and disposable files for safe cleanup."""
    root_str = params.get("path", "/data/data/com.termux/files/home")
    root = Path(root_str).expanduser().resolve()

    candidates: List[Dict[str, Any]] = []
    total_reclaimable_bytes = 0

    cache_patterns = [".cache", "__pycache__", ".pytest_cache", ".ruff_cache", "tmp", "temp", ".swp"]
    for r, dirs, files in os.walk(root):
        for d in dirs:
            if any(pat in d for pat in cache_patterns):
                target_dir = Path(r) / d
                try:
                    sz = sum(f.stat().st_size for f in target_dir.glob("**/*") if f.is_file())
                    candidates.append({
                        "path": str(target_dir),
                        "type": "cache_directory",
                        "size_mb": round(sz / (1024 * 1024), 2),
                    })
                    total_reclaimable_bytes += sz
                except Exception:
                    pass

    return {
        "success": True,
        "search_path": str(root),
        "candidates_count": len(candidates),
        "total_reclaimable_mb": round(total_reclaimable_bytes / (1024 * 1024), 2),
        "candidates": candidates,
    }
