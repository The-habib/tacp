# TACP Execution Contract Specification
## Deterministic, Cryptographically Bound Execution Contract

- **Standard:** TACP-SPEC-004-CONTRACT
- **Status:** APPROVED CONTRACT SPECIFICATION (GATE A)
- **Phase:** Phase 4 — Controlled Command Execution

---

## 1. Specification & Rationale

An execution contract represents the immutable, unambiguous, and deterministic specification of an operating-system command execution request.

In previous phases, approval tickets for filesystem patches bound to `patch_hash = sha256(canonical_diff)`. For command execution, approval must bind to the **entire execution context**. If an AI agent requests approval to run `printf "hello"` in `/workspace`, approving that request must never permit running `printf "%s" "$(malicious_var)"`, running in `/workspace/subdir`, running with an altered environment, or running with extended timeouts.

Therefore, every execution request is compiled into a canonical `ExecutionContract` and hashed using SHA-256.

---

## 2. The `ExecutionContract` Data Structure

```python
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class ExecutionContract:
    """Immutable specification of a governed execution request."""

    workspace_id: str
    executable: str
    argv: Tuple[str, ...]
    cwd: str
    environment: Tuple[Tuple[str, str], ...]
    network_enabled: bool
    timeout_seconds: int
    max_stdout_bytes: int
    max_stderr_bytes: int
```

### Field Definitions:
1. **`workspace_id` (str):** The unique identifier of the active TACP workspace.
2. **`executable` (str):** The canonical path to the resolved binary (e.g. `/data/data/com.termux/files/usr/bin/printf`).
3. **`argv` (Tuple[str, ...]):** The ordered tuple of argument strings passed to `execve()`. Note: `argv[0]` is typically the program name or full executable path.
4. **`cwd` (str):** The absolute, canonicalized, verified working directory where the process is spawned.
5. **`environment` (Tuple[Tuple[str, str], ...]):** The lexicographically sorted, deduplicated tuple of key-value environment pairs provided to the process.
6. **`network_enabled` (bool):** Boolean flag indicating whether network access is authorized (default `False`).
7. **`timeout_seconds` (int):** The hard watchdog timeout in seconds after which the process group is killed.
8. **`max_stdout_bytes` (int):** Hard limit on stdout bytes read before truncation.
9. **`max_stderr_bytes` (int):** Hard limit on stderr bytes read before truncation.

---

## 3. Canonical Hashing Algorithm

To guarantee platform-independent determinism, the contract hash is calculated via canonical JSON serialization:

```python
import hashlib
import json


def compute_execution_contract_hash(contract: ExecutionContract) -> str:
    """Compute deterministic SHA-256 hash for an ExecutionContract."""
    payload = {
        "workspace_id": contract.workspace_id,
        "executable": contract.executable,
        "argv": list(contract.argv),
        "cwd": contract.cwd,
        "environment": sorted([[k, v] for k, v in contract.environment]),
        "network_enabled": contract.network_enabled,
        "timeout_seconds": contract.timeout_seconds,
        "max_stdout_bytes": contract.max_stdout_bytes,
        "max_stderr_bytes": contract.max_stderr_bytes,
    }
    canonical_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()
```

### Properties of the Canonical Hash:
- **Collision Resistance:** SHA-256 provides 256 bits of cryptographic collision resistance.
- **Order Independence for Environment:** Environment variables are sorted lexicographically by key, preventing spurious mismatches from dictionary ordering.
- **Exact Vector Matching:** Argument order in `argv` is preserved exactly; altering argument position alters the hash.
- **Zero Ambiguity:** Separators are strictly fixed to `(`,`, `:`) with no trailing whitespace or formatting differences.

---

## 4. Invalidation Invariants

Any divergence between the approved contract and the submitted execution request immediately breaks hash verification:
- Changing a single character in any argument -> **DENY**.
- Adding or removing an argument -> **DENY**.
- Changing the working directory -> **DENY**.
- Changing an environment variable -> **DENY**.
- Changing the timeout -> **DENY**.
- Requesting execution in a different workspace -> **DENY**.

Approval is strictly single-use: upon verification, the ticket transitions to `STATUS_CONSUMED` and cannot be replayed.
