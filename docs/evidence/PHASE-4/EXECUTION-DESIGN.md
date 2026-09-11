# Phase 4 Evidence — Execution Design Architecture

**Document ID**: TACP-EV-P4-02  
**Status**: VERIFIED  
**Target Release**: v0.4.0-rc.1  

## 1. 16-Stage Governed Pipeline
The core execution engine implements the complete 16-stage deterministic security pipeline:

1. **Request Ingestion & Schema Validation**: Validate `workspace_id`, `executable`, `argv`, `timeout_seconds`.
2. **Feature Flag Check**: Enforce `execution_enabled == True`.
3. **Principal & Identity Context**: Bind caller principal ID (`local_agent`, `cli`, `mcp-client`).
4. **Policy Evaluation**: PolicyEngine verifies `execution.request` capability allowed for principal.
5. **Executable Resolution**: Deterministic resolution via `ExecutionResolver`, rejecting wildcards, traversal (`..`), null bytes, and non-whitelisted binaries.
6. **Workspace Containment**: Jail working directory (`cwd`) strictly within registered workspace root.
7. **Environment Assembly**: Build Base Safe Environment (curated PATH, safe HOME/TMPDIR/PWD/LANG), stripping secret patterns and forbidding system var overrides.
8. **Resource Limits & Watchdog Binding**: Bind hard execution timeout (capped at 60s) and buffer output limits (64KB stdout/stderr).
9. **Canonical ExecutionContract Hashing**: Compute deterministic SHA-256 hash across sorted contract fields.
10. **Approval Verification**: Verify and atomically consume scoped human approval ticket matching canonical contract hash.
11. **Dry-Run Short Circuit**: Return planned contract, resolved binary, and risk assessment without spawning process if `dry_run=True`.
12. **Audit Logging (Execution Initiated)**: Record state transition to `QUEUED` / `RUNNING` in audit log.
13. **Persistence (Execution Record Creation)**: Insert initial execution row in SQLite `executions` table.
14. **Process Spawning**: Spawn process via `ProcessExecutor` with `start_new_session=True` (setsid), `stdin=DEVNULL`, `shell=False`.
15. **Process Group Monitoring & Bounded I/O**: Stream non-blocking stdout/stderr reading, ANSI escape sequence scrubbing, truncation bounding, and watchdog timeout reaping (`os.killpg`).
16. **Post-Execution Finalization & Audit**: Record terminal status (`SUCCEEDED`, `FAILED`, `TIMED_OUT`, `CANCELLED`), exit code, signal, duration, and output metadata in database and audit chain.
