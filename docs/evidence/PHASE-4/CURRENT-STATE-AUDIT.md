# Phase 4 Evidence — Current State Audit

**Document ID**: TACP-EV-P4-01  
**Status**: VERIFIED  
**Target Release**: v0.4.0-rc.1  
**Scope**: Verification of controlled process execution implementation against security and containment specifications.

## 1. Executive Summary
Phase 4 introduces governed operating system process execution (`execution.request`) under strict containment, bounded I/O, scoped human approval, and deterministic binary resolution. Unlike traditional tools that invoke unrestricted shells (`bash -c`, `sh -c`, `os.system`), TACP establishes an unbypassable application-level security boundary with `shell=False` hardcoded into the execution core.

## 2. Capability Matrix State
- `workspace.inspect`: Read-only inspection (Phase 1)
- `workspace.patch`: Governed single-file patch (Phase 2 Slice 1)
- `workspace.patch_batch`: Governed multi-file batch patch (Phase 2 Slice 2)
- `execution.request`: Controlled process execution (Phase 4 Vertical Slice 1: `printf`, `echo`, `true`)

## 3. Verified Invariants
1. **Zero Shell Execution**: Neither `sh`, `bash`, `zsh`, `python`, nor arbitrary command strings can be invoked through `execution.request`.
2. **Immutable ExecutionContract**: Cryptographically bound canonical SHA-256 hash across executable, argv, cwd, environment, timeout, and limits.
3. **Fail-Closed Feature Flags**: `execution_enabled = False` by default in configuration.
4. **Process Group Containment**: `start_new_session=True` (setsid) ensures all subprocesses and descendant processes share an isolated process group (PGID == PID), reaped cleanly via `os.killpg(pgid, SIGKILL)` on timeout or cancellation.
5. **Hermetic Base Environment**: Dangerous environment variables (`LD_PRELOAD`, `PYTHONPATH`, token/secret patterns) are aggressively stripped. System variables (`PATH`, `HOME`, `PWD`, `TMPDIR`) cannot be overridden by callers.
6. **Scoped Human Approvals**: Approved bearer tickets are bound to the exact canonical `contract_hash`, single-use (`verify_and_consume`), non-replayable, and subject to 10-minute expiry.
7. **Tamper-Evident Audit Logging**: Every stage, lifecycle transition, and terminal execution event is recorded in the cryptographically chained SHA-256 SQLite audit trail.
