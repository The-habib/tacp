# TACP State Recovery, Checkpoints & Circuit Breakers

**Document:** `docs/execution/RECOVERY-MODEL.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**Execution Lead:** Antigravity Principal Execution Engineer  
**Date:** September 11, 2026  

---

## 1. Realistic Recovery Principles

1. **Honest Reversibility Guarantees**: TACP does not claim magic, arbitrary rollback for all operations. Operations are formally categorized by reversibility class:
   - **REVERSIBLE**: Pure file mutations inside workspace with pre-mutation snapshots. 100% rollback guarantee.
   - **PARTIALLY_REVERSIBLE**: Package installations (uninstallation may leave residual dependencies).
   - **IRREVERSIBLE**: External git commits pushed to remote, SMS messages sent via Termux API.
   - **EXTERNAL_SIDE_EFFECT**: Network webhooks, third-party API mutations.
2. **Crash-Resilient State**: System state is held in SQLite with Write-Ahead Logging (WAL) and `synchronous=NORMAL`. Unfinished operations are flagged and reconciled on startup.
3. **Fail-Stop Circuit Breaker**: If an automated workflow repeatedly fails, the system automatically suspends execution into `RECOVERY_REQUIRED` rather than thrashing in infinite retry loops.

---

## 2. Checkpoint & Snapshot Architecture

Before executing an `R2` or `R3` mutation within a workspace, TACP creates an immutable pre-mutation snapshot:

```
[Target File / Tree] ──────> Copy to ~/.tacp/snapshots/{snapshot_id}/
                                     │
                                     v
                        Metadata Record in SQLite
                        - snapshot_id: UUIDv4
                        - workspace_id: str
                        - file_manifest_json: {path: sha256}
                        - created_at: UTC timestamp
```

### Snapshot Primitives
- `snapshot.create(workspace_id, paths) -> snapshot_id`: Takes an atomic copy of targeted files.
- `snapshot.diff(snapshot_id) -> List[FileDiff]`: Compares current disk files to snapshot state.
- `snapshot.restore(snapshot_id) -> bool`: Atomically restores original files from snapshot store.

---

## 3. Crash Boundary Analysis & Recovery Actions

| Failure Point | System State at Crash | Automatic Recovery Behavior on Restart |
|---|---|---|
| **Before Mutation** | Temp file not created; target untouched | No action needed; contract marked `EXPIRED` |
| **During Temp File Write** | Incomplete `.tacp_tmp_*` on disk | Startup doctor purges orphaned `.tacp_tmp_*` files |
| **After Backup, Before Rename** | Snapshot recorded; target untouched | Snapshot retained; contract marked `FAILED` |
| **During `os.replace`** | Atomic rename in kernel | Either old or new file is intact; verified by checksum |
| **After Replace, Before Audit** | Target modified; audit log missing entry | Reconciliation engine detects disk/DB discrepancy |
| **During Background Job Run** | Child process killed by Android OOM | Process supervisor reconciles `JobStatus.FAILED` |

---

## 4. State Reconciliation Engine

During `tacp startup` or `tacp doctor`, the reconciliation engine aligns **Desired State** against **Observed State**:

```
+--------------------------+--------------------------+-------------------------------------+
| Desired State            | Observed State           | Safe Reconciliation Action          |
+--------------------------+--------------------------+-------------------------------------+
| Job is RUNNING           | Process PID dead         | Mark Job FAILED (OOM/Killed); alert |
| Job is RUNNING           | Process PID alive        | Re-attach monitoring stream         |
| Lock is ACQUIRED         | Holding process dead     | Release stale lock; record audit    |
| Lease is ACTIVE          | Expiration time elapsed  | Mark Lease EXPIRED                  |
| Approval is GRANTED      | Expiration time elapsed  | Mark Approval EXPIRED               |
+--------------------------+--------------------------+-------------------------------------+
```

*Rule*: TACP never automatically re-executes or restarts failed jobs unless the job policy explicitly defines an approved retry policy.

---

## 5. Circuit Breaker Mechanism

To prevent rogue AI loops from consuming battery, exhausting disk storage, or corrupting codebases:

```
[Operation Failure] ──> failure_count += 1
                              │
                              ├── If failure_count >= 4 consecutive failures:
                              │       │
                              │       v
                              │   [TRIP CIRCUIT BREAKER]
                              │       - Workspace state = 'RECOVERY_REQUIRED'
                              │       - All active agent leases SUSPENDED
                              │       - New mutations DENIED
                              │       - Human intervention required: 'tacp resume <ws>'
                              │
                              └── If operation succeeds:
                                      failure_count = 0
```
