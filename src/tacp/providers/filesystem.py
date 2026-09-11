"""Filesystem provider enforcing strict path jailing, classification, and output limits."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tacp.domain.classification import DataClassification
from tacp.domain.errors import (
    ErrorCode,
    TacpConflictError,
    TacpNotFoundError,
    TacpSecurityError,
    TacpValidationError,
)
from tacp.domain.patch import PatchStatus
from tacp.infrastructure.config import OutputLimits
from tacp.infrastructure.logging import redact_string

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

    def _resolve_in_jail(self, workspace_root: Path, subpath: str) -> Path:
        """Resolve a subpath within workspace_root, enforcing strict jail invariants."""
        if len(str(subpath)) > 4096:
            raise TacpSecurityError(
                ErrorCode.INVALID_INPUT,
                "Path exceeds maximum allowed length of 4096 characters",
            )

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
            "content": redact_string(content),
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
                                snippet_clean = redact_string(line.strip()[:200])
                                matches.append(
                                    {
                                        "file": rel_path,
                                        "line": idx,
                                        "snippet": snippet_clean,
                                        "line_content": snippet_clean,
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

    def _apply_unified_diff(self, orig_text: str, diff_text: str) -> Tuple[str, int, int]:
        orig_lines = orig_text.splitlines(keepends=True)
        diff_lines = diff_text.splitlines(keepends=True)

        hunk_regex = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
        i = 0
        while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
            i += 1

        if i >= len(diff_lines):
            raise TacpValidationError("Invalid patch format: no unified diff hunks found")

        result: List[str] = []
        orig_idx = 0
        added_count = 0
        removed_count = 0

        while i < len(diff_lines):
            m = hunk_regex.match(diff_lines[i])
            if not m:
                raise TacpValidationError(f"Invalid hunk header: {diff_lines[i].strip()}")

            old_start = int(m.group(1)) - 1
            if old_start < 0:
                old_start = 0

            while orig_idx < old_start and orig_idx < len(orig_lines):
                result.append(orig_lines[orig_idx])
                orig_idx += 1

            i += 1
            while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
                line = diff_lines[i]
                if line.startswith("+"):
                    result.append(line[1:])
                    added_count += 1
                elif line.startswith("-"):
                    if orig_idx >= len(orig_lines):
                        raise TacpValidationError(
                            "Hunk mismatch: expected line to remove at line "
                            f"{orig_idx + 1}, but file ended"
                        )
                    expected = orig_lines[orig_idx]
                    actual_del = line[1:]
                    if expected != actual_del and expected.rstrip("\r\n") != actual_del.rstrip(
                        "\r\n"
                    ):
                        raise TacpValidationError(
                            f"Hunk mismatch at line {orig_idx + 1}: "
                            f"expected {expected.rstrip()!r}, diff has {actual_del.rstrip()!r}"
                        )
                    orig_idx += 1
                    removed_count += 1
                elif line.startswith(" "):
                    if orig_idx >= len(orig_lines):
                        raise TacpValidationError(
                            "Hunk mismatch: expected context line at line "
                            f"{orig_idx + 1}, but file ended"
                        )
                    expected = orig_lines[orig_idx]
                    actual_ctx = line[1:]
                    if expected != actual_ctx and expected.rstrip("\r\n") != actual_ctx.rstrip(
                        "\r\n"
                    ):
                        raise TacpValidationError(
                            f"Hunk mismatch at line {orig_idx + 1}: "
                            f"expected context {expected.rstrip()!r}, "
                            f"diff has {actual_ctx.rstrip()!r}"
                        )
                    result.append(orig_lines[orig_idx])
                    orig_idx += 1
                elif line.startswith("\\"):
                    pass
                i += 1

        while orig_idx < len(orig_lines):
            result.append(orig_lines[orig_idx])
            orig_idx += 1

        return "".join(result), added_count, removed_count

    def apply_patch(
        self,
        workspace_root: Path,
        subpath: str,
        patch_diff: str,
        base_checksum: str,
        dry_run: bool = False,
        patch_id: Optional[str] = None,
        snapshot_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        raw_target = workspace_root / subpath.strip()
        if raw_target.is_symlink():
            raise TacpSecurityError(ErrorCode.OUTSIDE_WORKSPACE, "Cannot patch symlink")

        target = self._resolve_in_jail(workspace_root, subpath)

        if not target.exists():
            raise TacpNotFoundError(f"Target file does not exist: {subpath}")
        if target.is_dir():
            raise TacpValidationError(f"Target path is a directory, not a file: {subpath}")

        # Secret classification check
        if self.classify_file(target) in (
            DataClassification.SECRET,
            DataClassification.CRITICAL,
        ):
            raise TacpSecurityError(
                ErrorCode.POLICY_DENIED,
                f"Cannot patch protected/secret file '{target.name}'",
            )

        # Patch diff size limit
        diff_bytes = patch_diff.encode("utf-8")
        if len(diff_bytes) > self.limits.max_patch_bytes:
            raise TacpValidationError(
                f"Patch diff size ({len(diff_bytes)} bytes) exceeds limit "
                f"({self.limits.max_patch_bytes} bytes)"
            )

        # Existing file size limit
        target_size = target.stat().st_size
        if target_size > self.limits.max_file_size_bytes:
            raise TacpValidationError(
                f"File size ({target_size} bytes) exceeds limit "
                f"({self.limits.max_file_size_bytes} bytes)"
            )

        # Read target bytes & check for binary / null bytes
        try:
            file_bytes = target.read_bytes()
        except OSError as err:
            raise TacpSecurityError(
                ErrorCode.INTERNAL_ERROR, f"Failed to read target file: {err}"
            ) from err

        if b"\0" in file_bytes or "\0" in patch_diff:
            raise TacpValidationError(
                "Binary files or null bytes are not supported for patch operations"
            )

        try:
            orig_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError as err:
            raise TacpValidationError("Target file is not valid UTF-8 text") from err

        # Base checksum check (Optimistic Concurrency Control)
        current_checksum = hashlib.sha256(file_bytes).hexdigest()
        if base_checksum.lower().strip() != current_checksum.lower():
            raise TacpConflictError(
                f"Base checksum mismatch: expected '{base_checksum}', "
                f"current file checksum is '{current_checksum}'"
            )

        # Apply diff
        resulting_text, added_count, removed_count = self._apply_unified_diff(orig_text, patch_diff)

        resulting_bytes = resulting_text.encode("utf-8")
        if len(resulting_bytes) > self.limits.max_resulting_file_bytes:
            raise TacpValidationError(
                f"Resulting file size ({len(resulting_bytes)} bytes) exceeds limit "
                f"({self.limits.max_resulting_file_bytes} bytes)"
            )

        result_checksum = hashlib.sha256(resulting_bytes).hexdigest()
        pid = patch_id or f"patch-{uuid.uuid4().hex[:8]}"

        if dry_run:
            return {
                "patch_id": pid,
                "status": PatchStatus.SIMULATED,
                "subpath": subpath,
                "before_checksum": current_checksum,
                "after_checksum": result_checksum,
                "lines_added": added_count,
                "lines_removed": removed_count,
                "diff_preview": patch_diff[:500],
                "snapshot_path": None,
                "message": "Dry-run patch simulation succeeded",
            }

        # Live execution: Take snapshot first
        s_dir = snapshot_dir or (Path.home() / ".tacp" / "snapshots")
        snap_file = s_dir / pid / target.name
        try:
            snap_file.parent.mkdir(parents=True, exist_ok=True)
            snap_file.write_bytes(file_bytes)
            with snap_file.open("ab") as f:
                f.flush()
                os.fsync(f.fileno())
        except OSError as err:
            raise TacpSecurityError(
                ErrorCode.INTERNAL_ERROR,
                f"Failed to create pre-patch snapshot: {err}",
            ) from err

        # Atomic replacement in same parent directory to avoid EXDEV
        temp_file = target.parent / f".tacp_tmp_{uuid.uuid4().hex}"
        try:
            with temp_file.open("wb") as f:
                f.write(resulting_bytes)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, target)
        except Exception as err:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
            raise TacpSecurityError(
                ErrorCode.MUTATION_FAILED,
                f"Atomic patch write failed: {err}",
            ) from err

        # Post-write verification
        try:
            disk_bytes = target.read_bytes()
            disk_checksum = hashlib.sha256(disk_bytes).hexdigest()
            if disk_checksum != result_checksum:
                # Emergency rollback
                shutil.copy2(snap_file, target)
                raise TacpSecurityError(
                    ErrorCode.MUTATION_FAILED,
                    "Post-write verification failed: checksum mismatch; rolled back to snapshot",
                )
        except OSError as err:
            shutil.copy2(snap_file, target)
            raise TacpSecurityError(
                ErrorCode.MUTATION_FAILED,
                f"Post-write verification read failed: {err}; rolled back to snapshot",
            ) from err

        return {
            "patch_id": pid,
            "status": PatchStatus.APPLIED,
            "subpath": subpath,
            "before_checksum": current_checksum,
            "after_checksum": result_checksum,
            "lines_added": added_count,
            "lines_removed": removed_count,
            "diff_preview": patch_diff[:500],
            "snapshot_path": str(snap_file),
            "message": "Patch applied successfully",
        }

    def rollback_patch(
        self,
        workspace_root: Path,
        subpath: str,
        snapshot_path: Path,
        expected_current_checksum: Optional[str] = None,
    ) -> Dict[str, Any]:
        target = self._resolve_in_jail(workspace_root, subpath)
        if not snapshot_path.exists():
            raise TacpNotFoundError(f"Snapshot file not found: {snapshot_path}")

        if expected_current_checksum and target.exists():
            curr_bytes = target.read_bytes()
            curr_hash = hashlib.sha256(curr_bytes).hexdigest()
            if curr_hash != expected_current_checksum:
                raise TacpConflictError(
                    f"Rollback conflict: file checksum ({curr_hash}) "
                    f"does not match expected ({expected_current_checksum})"
                )

        snap_bytes = snapshot_path.read_bytes()
        temp_file = target.parent / f".tacp_tmp_{uuid.uuid4().hex}"
        try:
            with temp_file.open("wb") as f:
                f.write(snap_bytes)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, target)
        except Exception as err:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
            raise TacpSecurityError(
                ErrorCode.ROLLBACK_FAILED,
                f"Rollback atomic restore failed: {err}",
            ) from err

        restored_hash = hashlib.sha256(snap_bytes).hexdigest()
        return {
            "status": PatchStatus.ROLLED_BACK,
            "subpath": subpath,
            "restored_checksum": restored_hash,
            "message": "File successfully rolled back from snapshot",
        }

    # Compatibility aliases
    resolve_safe_path = _resolve_in_jail
    _classify_path = classify_file
