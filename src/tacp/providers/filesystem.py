"""Filesystem provider enforcing strict path jailing, classification, and output limits."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from tacp.domain.classification import DataClassification
from tacp.domain.errors import ErrorCode, TacpNotFoundError, TacpSecurityError
from tacp.infrastructure.config import OutputLimits

SECRET_EXTENSIONS = {".env", ".key", ".pem", ".token", ".crt", ".pfx", ".p12"}
SECRET_FILENAMES = {
    "id_rsa",
    "id_ed25519",
    "credentials.json",
    ".bash_history",
    ".gitconfig",
    ".env",
}
SECRET_PATTERNS = [
    re.compile(r"-----(BEGIN|END) [A-Z ]+ PRIVATE KEY-----"),
    re.compile(r"ghp_[A-Za-z0-9_]{36,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{82,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{32,}"),
    re.compile(r"ya29\.[A-Za-z0-9_-]+"),
]


class FilesystemProvider:
    """Provides path jailing, reading, listing, and searching inside authorized workspaces."""

    def __init__(self, limits: Optional[OutputLimits] = None) -> None:
        self.limits = limits or OutputLimits()

    def resolve_safe_path(self, workspace_root: Path, subpath: str) -> Path:
        # Null-byte and URL-encoding defenses
        if "\0" in subpath or "%" in subpath:
            raise TacpSecurityError(
                ErrorCode.OUTSIDE_WORKSPACE,
                "Null or encoded characters detected in path specification",
            )

        resolved_root = workspace_root.resolve()
        if not resolved_root.exists():
            raise TacpNotFoundError(f"Workspace root does not exist: {workspace_root}")

        cleaned = subpath.strip()
        if cleaned in ("", "/"):
            return resolved_root

        # Reject absolute paths attempting to access root filesystem
        if cleaned.startswith("/"):
            raise TacpSecurityError(
                ErrorCode.OUTSIDE_WORKSPACE,
                f"Absolute path '{subpath}' escapes authorized workspace boundary",
            )

        target = (resolved_root / cleaned).resolve()

        # Workspace containment check (canonical path jail)
        try:
            target.relative_to(resolved_root)
        except ValueError as err:
            raise TacpSecurityError(
                ErrorCode.OUTSIDE_WORKSPACE,
                f"Path '{subpath}' escapes authorized workspace boundary",
            ) from err

        # Symlink boundary check
        raw_path = resolved_root / cleaned
        if raw_path.is_symlink():
            try:
                symlink_target = raw_path.resolve()
                symlink_target.relative_to(resolved_root)
            except ValueError as err:
                raise TacpSecurityError(
                    ErrorCode.OUTSIDE_WORKSPACE,
                    f"Symlink '{subpath}' resolves outside authorized workspace",
                ) from err

        return target

    def classify_file(self, path: Path) -> DataClassification:
        name_lower = path.name.lower()
        if (
            name_lower.startswith(".env")
            or name_lower in SECRET_FILENAMES
            or path.suffix.lower() in SECRET_EXTENSIONS
        ):
            return DataClassification.SECRET

        # Fast scan for obvious secret patterns in small files
        try:
            if path.is_file() and path.stat().st_size < 32768:
                content = path.read_text(errors="ignore")
                for pattern in SECRET_PATTERNS:
                    if pattern.search(content):
                        return DataClassification.SECRET
        except (OSError, UnicodeDecodeError):
            pass

        if ".git" in path.parts:
            return DataClassification.INTERNAL

        return DataClassification.PUBLIC

    def list_dir(self, workspace_root: Path, subpath: str = "") -> Dict[str, Any]:
        target = self.resolve_safe_path(workspace_root, subpath)
        if not target.exists():
            raise TacpNotFoundError(f"Directory not found: {subpath}")
        if not target.is_dir():
            raise TacpSecurityError(
                ErrorCode.INVALID_INPUT, f"Target is not a directory: {subpath}"
            )

        entries: List[Dict[str, Any]] = []
        truncated = False
        all_items = sorted(list(target.iterdir()), key=lambda p: p.name)

        total_count = len(all_items)
        if total_count > self.limits.max_dir_entries:
            all_items = all_items[: self.limits.max_dir_entries]
            truncated = True

        for p in all_items:
            try:
                stat = p.stat()
                entries.append(
                    {
                        "name": p.name,
                        "is_dir": p.is_dir(),
                        "is_symlink": p.is_symlink(),
                        "size_bytes": stat.st_size,
                        "mtime": stat.st_mtime,
                        "classification": self.classify_file(p).value,
                    }
                )
            except OSError:
                continue

        return {
            "path": subpath,
            "entries": entries,
            "total_count": total_count,
            "truncated": truncated,
            "limit": self.limits.max_dir_entries,
        }

    def stat_path(self, workspace_root: Path, subpath: str) -> Dict[str, Any]:
        target = self.resolve_safe_path(workspace_root, subpath)
        if not target.exists() and not target.is_symlink():
            raise TacpNotFoundError(f"Path not found: {subpath}")

        try:
            stat = target.stat()
        except OSError as exc:
            raise TacpSecurityError(
                ErrorCode.PROVIDER_ERROR, f"Failed to stat path: {exc}"
            ) from exc

        classification = self.classify_file(target)
        return {
            "path": subpath,
            "exists": True,
            "is_dir": target.is_dir(),
            "is_file": target.is_file(),
            "is_symlink": target.is_symlink(),
            "size_bytes": stat.st_size,
            "permissions": oct(stat.st_mode),
            "mtime": stat.st_mtime,
            "classification": classification.value,
        }

    def read_file(self, workspace_root: Path, subpath: str) -> Dict[str, Any]:
        target = self.resolve_safe_path(workspace_root, subpath)
        if not target.exists():
            raise TacpNotFoundError(f"File not found: {subpath}")
        if not target.is_file():
            raise TacpSecurityError(ErrorCode.INVALID_INPUT, f"Path is not a file: {subpath}")

        classification = self.classify_file(target)
        if classification in [DataClassification.SECRET, DataClassification.CRITICAL]:
            raise TacpSecurityError(
                ErrorCode.SECRET_PROTECTED,
                f"Access denied: file '{subpath}' is classified as {classification.value}",
            )

        # Binary file defense
        try:
            with target.open("rb") as bf:
                chunk = bf.read(1024)
                if b"\x00" in chunk:
                    raise TacpSecurityError(
                        ErrorCode.RESOURCE_LIMIT,
                        f"Binary file cannot be read in text mode: {subpath}",
                    )
        except TacpSecurityError:
            raise
        except Exception as exc:
            raise TacpSecurityError(
                ErrorCode.PROVIDER_ERROR, f"Failed to check file: {exc}"
            ) from exc

        total_bytes = target.stat().st_size
        truncated = False

        try:
            with target.open("r", encoding="utf-8", errors="replace") as f:
                content = f.read(self.limits.max_file_read_bytes)
                if f.read(1):  # More content exists
                    truncated = True
        except Exception as exc:
            raise TacpSecurityError(
                ErrorCode.PROVIDER_ERROR, f"Failed to read file: {exc}"
            ) from exc

        bytes_read = len(content.encode("utf-8"))
        return {
            "path": subpath,
            "content": content,
            "bytes_read": bytes_read,
            "truncated": truncated,
            "total_bytes": total_bytes,
            "total_size_bytes": total_bytes,
        }

    def search_files(
        self,
        workspace_root: Path,
        query: str,
        subpath: str = "",
        case_sensitive: bool = False,
    ) -> Dict[str, Any]:
        target = self.resolve_safe_path(workspace_root, subpath)
        if not target.exists():
            raise TacpNotFoundError(f"Directory not found: {subpath}")
        if not target.is_dir():
            raise TacpSecurityError(
                ErrorCode.INVALID_INPUT, f"Target is not a directory: {subpath}"
            )

        matches: List[Dict[str, Any]] = []
        truncated = False
        target_query = query if case_sensitive else query.lower()

        for path in target.rglob("*"):
            if path.is_file() and not path.is_symlink():
                # Skip classified secret files in search results
                if self.classify_file(path) in [
                    DataClassification.SECRET,
                    DataClassification.CRITICAL,
                ]:
                    continue

                try:
                    rel_path = str(path.relative_to(workspace_root))
                    with path.open("r", encoding="utf-8", errors="ignore") as f:
                        for idx, line in enumerate(f, start=1):
                            comp_line = line if case_sensitive else line.lower()
                            if target_query in comp_line:
                                matches.append(
                                    {
                                        "file": rel_path,
                                        "line": idx,
                                        "snippet": line.strip()[:200],
                                    }
                                )
                                if len(matches) >= self.limits.max_search_results:
                                    truncated = True
                                    return {
                                        "query": query,
                                        "matches": matches,
                                        "total_matches": len(matches),
                                        "truncated": True,
                                    }
                except OSError:
                    continue

        return {
            "query": query,
            "matches": matches,
            "total_matches": len(matches),
            "truncated": truncated,
        }

    # Compatibility aliases
    _resolve_in_jail = resolve_safe_path
    _classify_path = classify_file
