# TACP Phase 5: Execution Contract and Result Integrity
**Document ID:** `TACP-EXEC-CTR-001`  
**Classification:** Core Protocol & Cryptographic Specification  
**Release Target:** v0.4.0-rc.1 Hardening / Phase 5  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Cryptographic Contract Binding

In TACP, no execution may occur without an immutable, cryptographically bound specification known as the `ExecutionContract`.

### 1.1 Complete Security Property Set
Every parameter that affects execution security or behavior is bound into the contract:
- `contract_version`: Integer protocol version (currently `1`).
- `workspace_id`: The unique workspace identifier.
- `executable`: The canonical path to the resolved binary.
- `executable_digest`: The SHA-256 digest of the binary file content.
- `argv`: The complete, validated argument vector.
- `cwd`: The validated working directory within the workspace jail.
- `environment`: The complete lexicographically sorted key-value pairs of the safe environment.
- `network_enabled`: Boolean network flag.
- `network_state`: Explicit truth model state (`NETWORK_UNENFORCED`).
- `timeout_seconds`: Bound wall-clock duration limit.
- `max_stdout_bytes`: Hard byte cap for standard output.
- `max_stderr_bytes`: Hard byte cap for standard error.
- `principal_id`: The identity of the requesting principal.

### 1.2 Canonical Hashing Algorithm
The contract hash is computed by deterministic JSON serialization with sorted keys and zero extraneous whitespace, hashed via SHA-256:
```python
def compute_execution_contract_hash(contract: ExecutionContract) -> str:
    payload = {
        "argv": list(contract.argv),
        "contract_version": contract.contract_version,
        "cwd": contract.cwd,
        "environment": sorted([[k, v] for k, v in contract.environment]),
        "executable": contract.executable,
        "executable_digest": contract.executable_digest or "",
        "max_stderr_bytes": contract.max_stderr_bytes,
        "max_stdout_bytes": contract.max_stdout_bytes,
        "network_enabled": contract.network_enabled,
        "network_state": contract.network_state,
        "principal_id": contract.principal_id or "",
        "timeout_seconds": contract.timeout_seconds,
        "workspace_id": contract.workspace_id,
    }
    canonical_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()
```

**Security Invariant:** Altering any parameter (even 1 character in argv, cwd, or environment) alters the SHA-256 hash. If human approval was granted for hash $H_1$, executing with modified parameters $H_2$ fails fail-closed with `TacpSecurityError(ErrorCode.NOT_AUTHORIZED)`.

---

## 2. Result Integrity & Status Taxonomy

The `ExecutionResult` captures the deterministic post-execution reality.

### 2.1 Formal Status Codes (`ExecutionStatus`)
- `SUCCEEDED`: Process completed naturally with exit code 0, no timeouts, no output limit breaches, and no termination signals.
- `FAILED`: Process exited with non-zero exit code or terminated with an error during spawn/runtime.
- `TIMED_OUT`: Process exceeded contractual wall-clock timeout and was terminated via SIGTERM/SIGKILL.
- `OUTPUT_LIMIT_EXCEEDED`: Process exceeded contractual stdout or stderr byte caps and was terminated under Model B governance.
- `CANCELLED`: Process was intentionally aborted by an authorized operator via `cancel_execution()` or `emergency_stop()`.
- `ORPHANED`: Process was found running during startup reconciliation without an active supervisor.
- `DRY_RUN`: Request was simulated without spawning OS processes.

### 2.2 Prohibited False Success Invariants
1. An execution terminated by timeout or signal can **never** report `SUCCEEDED`.
2. An execution terminated due to output overflow can **never** report `SUCCEEDED`.
3. An orphaned or recovered execution can **never** report `SUCCEEDED`.
