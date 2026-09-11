"""Domain entities for workspace patch operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class PatchStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPLIED = "APPLIED"
    SIMULATED = "SIMULATED"
    CONFLICT = "CONFLICT"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    DENIED = "DENIED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass(frozen=True)
class WorkspacePatch:
    patch_id: str
    workspace_id: str
    subpath: str
    base_checksum: str
    patch_content: str
    dry_run: bool = False
    principal_id: str = "anonymous"
    created_at: str = ""
    approval_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "workspace_id": self.workspace_id,
            "subpath": self.subpath,
            "base_checksum": self.base_checksum,
            "dry_run": self.dry_run,
            "principal_id": self.principal_id,
            "created_at": self.created_at,
            "approval_id": self.approval_id,
        }


@dataclass(frozen=True)
class PatchResult:
    patch_id: str
    status: PatchStatus
    subpath: str
    before_checksum: str
    after_checksum: str
    lines_added: int = 0
    lines_removed: int = 0
    diff_preview: str = ""
    audit_id: str = ""
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "status": self.status.value,
            "subpath": self.subpath,
            "before_checksum": self.before_checksum,
            "after_checksum": self.after_checksum,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "diff_preview": self.diff_preview,
            "audit_id": self.audit_id,
            "message": self.message,
            "details": self.details,
        }


@dataclass(frozen=True)
class BatchPatchItem:
    subpath: str
    patch_content: str
    base_checksum: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subpath": self.subpath,
            "patch_content": self.patch_content,
            "base_checksum": self.base_checksum,
        }


@dataclass(frozen=True)
class BatchPatchResult:
    batch_id: str
    status: PatchStatus
    workspace_id: str
    results: list[PatchResult] = field(default_factory=list)
    audit_id: str = ""
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def changed_files(self) -> list[str]:
        return [r.subpath for r in self.results]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "status": self.status.value,
            "workspace_id": self.workspace_id,
            "changed_files": self.changed_files,
            "results": [r.to_dict() for r in self.results],
            "audit_id": self.audit_id,
            "message": self.message,
            "details": self.details,
        }
