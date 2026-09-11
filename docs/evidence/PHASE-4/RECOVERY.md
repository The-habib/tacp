# Phase 4 Evidence — Crash Recovery & Orphan Reconciliation

**Document ID**: TACP-EV-P4-15  
**Status**: VERIFIED  
**Target Release**: v0.4.0-rc.1  

## 1. Crash Consistency
If the TACP daemon or host process unexpectedly terminates mid-execution:
- SQLite WAL mode guarantees transactional durability.
- Upon startup, `ExecutionService.reconcile_orphans()` scans the database for executions stuck in non-terminal states (`RUNNING`, `QUEUED`).
- For each dangling execution:
  - If the recorded PID is dead (`/proc/<pid>` does not exist), the status is transitioned to `FAILED` or `ORPHANED`.
  - If the recorded PID is alive, it is reaped via process group termination (`SIGKILL`).
- Tested via `tests/unit/test_execution_sabotage.py::test_sabotage_orphan_reconciliation` (**PASS**).
- Emergency stop command (`tacp execution emergency-stop`) terminates all active execution process groups in one sweep.
