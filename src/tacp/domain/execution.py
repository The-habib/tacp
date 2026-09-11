"""Domain models and data structures for controlled OS process execution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ExecutionStatus(str, Enum):
    CREATED = "CREATED"
    DRY_RUN = "DRY_RUN"
    VALIDATING = "VALIDATING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    TERMINATING = "TERMINATING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    OUTPUT_LIMIT_EXCEEDED = "OUTPUT_LIMIT_EXCEEDED"
    CANCELLED = "CANCELLED"
    ORPHANED = "ORPHANED"
    RECOVERING = "RECOVERING"


class CommandRiskLevel(str, Enum):
    SAFE = "SAFE"
    CONTROLLED = "CONTROLLED"
    DANGEROUS = "DANGEROUS"
    CRITICAL = "CRITICAL"


class NetworkIsolationState(str, Enum):
    NETWORK_DENIED = "NETWORK_DENIED"
    NETWORK_ALLOWED = "NETWORK_ALLOWED"
    NETWORK_UNENFORCED = "NETWORK_UNENFORCED"
    NETWORK_UNKNOWN = "NETWORK_UNKNOWN"


@dataclass(frozen=True)
class ExecutionContract:
    """Immutable, cryptographically bound execution specification."""

    workspace_id: str
    executable: str
    argv: Tuple[str, ...]
    cwd: str
    environment: Tuple[Tuple[str, str], ...]
    network_enabled: bool
    timeout_seconds: int
    max_stdout_bytes: int
    max_stderr_bytes: int
    contract_version: int = 1
    network_state: str = NetworkIsolationState.NETWORK_UNENFORCED.value
    executable_digest: Optional[str] = None
    principal_id: Optional[str] = None


def compute_execution_contract_hash(contract: ExecutionContract) -> str:
    """Compute deterministic canonical SHA-256 hash for an ExecutionContract."""
    payload = {
        "argv": list(contract.argv),
        "contract_version": contract.contract_version,
        "cwd": str(contract.cwd),
        "environment": sorted([[k, v] for k, v in contract.environment]),
        "executable": str(contract.executable),
        "executable_digest": contract.executable_digest or "",
        "max_stderr_bytes": contract.max_stderr_bytes,
        "max_stdout_bytes": contract.max_stdout_bytes,
        "network_enabled": contract.network_enabled,
        "network_state": contract.network_state,
        "principal_id": contract.principal_id or "",
        "timeout_seconds": contract.timeout_seconds,
        "workspace_id": str(contract.workspace_id),
    }
    canonical_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of an execution attempt or dry-run simulation."""

    execution_id: str
    status: str
    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration_ms: int
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    timed_out: bool = False
    cancelled: bool = False
    output_limit_exceeded: bool = False
    contract_hash: str = ""
    pid: Optional[int] = None
    pgid: Optional[int] = None
    term_signal: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "status": self.status,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
            "timed_out": self.timed_out,
            "cancelled": self.cancelled,
            "output_limit_exceeded": self.output_limit_exceeded,
            "contract_hash": self.contract_hash,
            "pid": self.pid,
            "pgid": self.pgid,
            "term_signal": self.term_signal,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class ExecutionRecord:
    """Durable database record representing an execution."""

    id: str
    execution_id: str
    action_type: str
    workspace_id: str
    executable: str
    argv: List[str]
    cwd: str
    contract_hash: str
    principal_id: str
    status: str
    created_at: str
    exit_code: Optional[int] = None
    term_signal: Optional[int] = None
    duration_ms: Optional[int] = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    timed_out: bool = False
    cancelled: bool = False
    output_limit_exceeded: bool = False
    pid: Optional[int] = None
    pgid: Optional[int] = None
    started_at: Optional[str] = None
    terminated_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
