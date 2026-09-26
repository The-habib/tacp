"""Handlers for filesystem.* namespace capabilities."""

from __future__ import annotations

import base64
import fnmatch
import hashlib
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List

from tacp.backends.base import BaseBackend


def _resolve_path(raw_path: str) -> Path:
    """Resolve path expanding user home."""
    return Path(raw_path).expanduser().resolve()


def handle_fs_list(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """List directory entries with detailed file metadata."""
    path_str = params.get("path", ".")
    target = _resolve_path(path_str)

    if not target.exists():
        return {"success": False, "error": f"Path not found: {path_str}"}
    if not target.is_dir():
        return {"success": False, "error": f"Path is not a directory: {path_str}"}

    entries: List[Dict[str, Any]] = []
    limit = int(params.get("limit", 200))
    try:
        for p in sorted(target.iterdir()):
            try:
                st = p.stat()
                entries.append(
                    {
                        "name": p.name,
                        "path": str(p),
                        "is_dir": p.is_dir(),
                        "is_file": p.is_file(),
                        "is_symlink": p.is_symlink(),
                        "size_bytes": st.st_size if not p.is_dir() else 0,
                        "modified_time": st.st_mtime,
                        "mode": oct(st.st_mode),
                    }
                )
            except Exception:
                entries.append({"name": p.name, "path": str(p), "accessible": False})

            if len(entries) >= limit:
                break
    except Exception as exc:
        return {"success": False, "error": f"Failed to list directory: {exc}"}

    return {"success": True, "path": str(target), "count": len(entries), "entries": entries}


def handle_fs_stat(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Get detailed metadata for a file or directory."""
    path_str = params.get("path")
    if not path_str:
        return {"success": False, "error": "Missing required parameter 'path'"}

    target = _resolve_path(path_str)
    if not target.exists():
        return {"success": False, "error": f"Path not found: {path_str}"}

    try:
        st = target.stat()
        return {
            "success": True,
            "path": str(target),
            "name": target.name,
            "is_dir": target.is_dir(),
            "is_file": target.is_file(),
            "is_symlink": target.is_symlink(),
            "size_bytes": st.st_size,
            "created_time": getattr(st, "st_ctime", st.st_mtime),
            "modified_time": st.st_mtime,
            "accessed_time": st.st_atime,
            "mode": oct(st.st_mode),
            "uid": st.st_uid,
            "gid": st.st_gid,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def handle_fs_read(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Safely read content from a file with offset and limit."""
    path_str = params.get("path")
    if not path_str:
        return {"success": False, "error": "Missing required parameter 'path'"}

    target = _resolve_path(path_str)
    if not target.exists() or not target.is_file():
        return {"success": False, "error": f"File not found: {path_str}"}

    max_bytes = int(params.get("max_bytes", 512 * 1024))  # 512KB default limit
    offset = int(params.get("offset", 0))
    as_base64 = bool(params.get("base64", False))

    try:
        file_size = target.stat().st_size
        with open(target, "rb") as f:
            if offset > 0:
                f.seek(offset)
            chunk = f.read(max_bytes)

        if as_base64:
            content_str = base64.b64encode(chunk).decode("ascii")
            encoding = "base64"
        else:
            content_str = chunk.decode("utf-8", errors="replace")
            encoding = "utf-8"

        truncated = (offset + len(chunk)) < file_size
        return {
            "success": True,
            "path": str(target),
            "size_bytes": file_size,
            "bytes_read": len(chunk),
            "offset": offset,
            "truncated": truncated,
            "encoding": encoding,
            "content": content_str,
        }
    except Exception as exc:
        return {"success": False, "error": f"Failed to read file: {exc}"}


def handle_fs_write(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Write text or base64 data to a file."""
    path_str = params.get("path")
    content = params.get("content")
    if not path_str or content is None:
        return {"success": False, "error": "Missing required parameter 'path' or 'content'"}

    target = _resolve_path(path_str)
    is_base64 = bool(params.get("base64", False))

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if is_base64:
            data = base64.b64decode(content)
            with open(target, "wb") as f:
                f.write(data)
            bytes_written = len(data)
        else:
            text = str(content)
            with open(target, "w", encoding="utf-8") as f:
                f.write(text)
            bytes_written = len(text.encode("utf-8"))

        return {
            "success": True,
            "path": str(target),
            "bytes_written": bytes_written,
        }
    except Exception as exc:
        return {"success": False, "error": f"Failed to write file: {exc}"}


def handle_fs_append(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Append text to an existing or new file."""
    path_str = params.get("path")
    content = params.get("content")
    if not path_str or content is None:
        return {"success": False, "error": "Missing required parameter 'path' or 'content'"}

    target = _resolve_path(path_str)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            f.write(str(content))
        return {"success": True, "path": str(target)}
    except Exception as exc:
        return {"success": False, "error": f"Failed to append to file: {exc}"}


def handle_fs_copy(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Copy file or directory tree."""
    src = _resolve_path(params.get("source", ""))
    dst = _resolve_path(params.get("destination", ""))

    if not src.exists():
        return {"success": False, "error": f"Source does not exist: {src}"}

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        return {"success": True, "source": str(src), "destination": str(dst)}
    except Exception as exc:
        return {"success": False, "error": f"Failed to copy: {exc}"}


def handle_fs_move(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Move or rename file or directory."""
    src = _resolve_path(params.get("source", ""))
    dst = _resolve_path(params.get("destination", ""))

    if not src.exists():
        return {"success": False, "error": f"Source does not exist: {src}"}

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"success": True, "source": str(src), "destination": str(dst)}
    except Exception as exc:
        return {"success": False, "error": f"Failed to move: {exc}"}


def handle_fs_delete(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Delete file or directory."""
    target = _resolve_path(params.get("path", ""))
    if not target.exists():
        return {"success": False, "error": f"Target not found: {target}"}

    recursive = bool(params.get("recursive", False))
    try:
        if target.is_dir():
            if recursive:
                shutil.rmtree(target)
            else:
                target.rmdir()
        else:
            target.unlink()
        return {"success": True, "deleted": str(target)}
    except Exception as exc:
        return {"success": False, "error": f"Failed to delete: {exc}"}


def handle_fs_mkdir(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Create directory path including parent directories."""
    target = _resolve_path(params.get("path", ""))
    try:
        target.mkdir(parents=True, exist_ok=True)
        return {"success": True, "path": str(target)}
    except Exception as exc:
        return {"success": False, "error": f"Failed to create directory: {exc}"}


def handle_fs_find(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Find files matching glob pattern."""
    root = _resolve_path(params.get("path", "."))
    pattern = params.get("pattern", "*")
    limit = int(params.get("limit", 100))

    if not root.exists() or not root.is_dir():
        return {"success": False, "error": f"Directory not found: {root}"}

    matches: List[str] = []
    try:
        for r, _, files in os.walk(root):
            for f in files:
                if fnmatch.fnmatch(f, pattern):
                    matches.append(os.path.join(r, f))
                    if len(matches) >= limit:
                        break
            if len(matches) >= limit:
                break
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    return {"success": True, "pattern": pattern, "count": len(matches), "matches": matches}


def handle_fs_hash(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Compute cryptographic hash of a file (sha256, md5, sha1)."""
    target = _resolve_path(params.get("path", ""))
    algo = params.get("algorithm", "sha256").lower()

    if not target.exists() or not target.is_file():
        return {"success": False, "error": f"File not found: {target}"}

    h = (
        hashlib.sha256()
        if algo == "sha256"
        else (
            hashlib.md5(usedforsecurity=False)  # noqa: S324
            if algo == "md5"
            else hashlib.sha1(usedforsecurity=False)  # noqa: S324
        )
    )
    try:
        with open(target, "rb") as f:
            while chunk := f.read(64 * 1024):
                h.update(chunk)
        return {
            "success": True,
            "path": str(target),
            "algorithm": algo,
            "hash": h.hexdigest(),
            "size_bytes": target.stat().st_size,
        }
    except Exception as exc:
        return {"success": False, "error": f"Hash computation error: {exc}"}


def handle_fs_zip(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Compress files or directory into zip archive."""
    source = _resolve_path(params.get("source", ""))
    archive = _resolve_path(params.get("archive_path", ""))

    if not source.exists():
        return {"success": False, "error": f"Source not found: {source}"}

    archive.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    try:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            if source.is_dir():
                for r, _, files in os.walk(source):
                    for f in files:
                        full = Path(r) / f
                        arcname = full.relative_to(source)
                        zf.write(full, arcname)
                        count += 1
            else:
                zf.write(source, source.name)
                count += 1
        return {
            "success": True,
            "archive": str(archive),
            "files_compressed": count,
            "size_bytes": archive.stat().st_size,
        }
    except Exception as exc:
        return {"success": False, "error": f"Zip failed: {exc}"}


def handle_fs_unzip(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Extract zip archive into destination directory."""
    archive = _resolve_path(params.get("archive_path", ""))
    destination = _resolve_path(params.get("destination", "."))

    if not archive.exists():
        return {"success": False, "error": f"Archive not found: {archive}"}

    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(destination)
            count = len(zf.namelist())
        return {"success": True, "destination": str(destination), "files_extracted": count}
    except Exception as exc:
        return {"success": False, "error": f"Unzip failed: {exc}"}
