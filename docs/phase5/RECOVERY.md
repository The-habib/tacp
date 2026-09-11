# TACP Phase 5: Crash Recovery and Emergency Stop
**Document ID:** `TACP-REC-EMERG-001`  
**Classification:** Operational Resiliency Specification  
**Release Target:** v0.4.0-rc.1 Hardening / Phase 5  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Crash Failure Modes & Recovery Matrix

TACP accounts for abrupt supervisor termination (power loss, Android LMK, unhandled exceptions) across all 10 execution lifecycle stages:

| Lifecycle Stage | Crash Event | State on Restart | Recovery Action (`reconcile_orphans`) | Invariant Guarantee |
| :--- | :--- | :--- | :--- | :--- |
| **1. Request Ingestion** | Crash before validation | Zero database trace | Client receives transport error / connection reset | No ghost state |
| **2. Policy Evaluation** | Crash during policy check | Zero database trace | Client reconnects, policy re-evaluated | Zero unauthorized execution |
| **3. Approval Gate** | Crash after ticket creation | Ticket in `PENDING` | Ticket expires naturally after TTL | Unapproved tickets never execute |
| **4. Pre-Persistence** | Crash before SQL INSERT | Zero database record | Clean state | No unmonitored execution |
| **5. Pre-Spawn** | Crash after INSERT (`RUNNING`), before `Popen` | DB status `RUNNING`, PID is NULL | `reconcile_orphans` detects PID is NULL -> Marks `FAILED` | False success impossible |
| **6. Active Execution** | Crash while child is running | DB status `RUNNING`, PID registered | Probes `/proc/<pid>`. If alive, marks `ORPHANED`. If dead, marks `FAILED`. | Unknown state cannot become success |
| **7. Timeout / Signal** | Crash during `os.killpg` | DB status `RUNNING`, process may be terminating | Reconciler re-checks `/proc/<pid>` and marks `FAILED` | Closed fail-safe |
| **8. Child Exit** | Crash before reading pipes | DB status `RUNNING`, process dead | Reconciler marks `FAILED` | Never claims `SUCCEEDED` without stream verification |
| **9. Post-Persistence** | Crash after `UPDATE executions` | DB status is terminal (`SUCCEEDED`/`FAILED`) | Intact transaction, no action needed | Durable SQLite WAL semantics |
| **10. Audit Append** | Crash before audit append | Audit chain intact at previous block | Audit verify detects gap or transaction rollbacks | Hash chain integrity maintained |

---

## 2. Emergency Stop Subsystem

The Emergency Stop protocol provides an immediate, auditable, global kill-switch across the entire control plane.

### 2.1 Invocation Protocol
- **CLI Command:** `tacp execution emergency-stop`
- **Authority Requirement:** Requires `PrincipalType.HUMAN`, `TrustTier.PRIVILEGED`, or `Authority.ADMIN_EMERGENCY_STOP`. Unprivileged agents are denied.

### 2.2 Execution Semantics
1. **Target Identification:** Enumerates all processes in the in-memory active registry (`ProcessExecutor.get_all_active()`).
2. **Signal Propagation:** Dispatches `SIGTERM` followed by immediate `SIGKILL` to each active process group (`os.killpg(active.pgid, ...)`).
3. **Database Reconciliation:** Updates all active execution records in SQLite (`RUNNING`, `STARTING`, `QUEUED`) to `CANCELLED`.
4. **Cryptographic Audit Event:** Appends an un-tamperable audit event (`execution.emergency_stop`) to the SHA-256 audit hash chain.
5. **Idempotence:** Safe to call repeatedly and concurrently; dead processes are ignored gracefully via `ProcessLookupError` handling.
