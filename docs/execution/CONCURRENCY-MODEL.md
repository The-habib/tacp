# TACP Concurrency Control, Locking & Capability Leases

**Document:** `docs/execution/CONCURRENCY-MODEL.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**Execution Lead:** Antigravity Principal Execution Engineer  
**Date:** September 11, 2026  

---

## 1. Concurrency Principles

1. **No Silent Overwrites**: If a human developer or another agent edits a file, concurrent operations must detect the mismatch and abort with a structured conflict rather than overwriting.
2. **Explicit Lock Ownership**: Every lock is bound to a specific `Principal` and `ExecutionContract`.
3. **Deadlock Immunity via Lock Hierarchy**: When multiple resources are required, locks must be acquired in lexicographical canonical path order. Nested lock acquisition across workspaces is forbidden.
4. **Stale Lock Pruning**: Locks feature a hard Time-to-Live (TTL). If a holding process dies without unlocking, the lock automatically expires.

---

## 2. Lock Hierarchy & Scopes

```
[WORKSPACE LOCK]    --> Exclusive or Shared lock on entire workspace directory
        │
        v
  [FILE LOCK]       --> Fine-grained lock on a specific canonical file path
```

| Lock Type | Mode | Intended Use | Conflict Rule |
|---|---|---|---|
| **Workspace Shared (S)** | Read | Directory scanning, search, multiple concurrent reads | Allows other (S); blocks Exclusive (X) |
| **Workspace Exclusive (X)**| Write | Major refactors, multi-file patches, git branch switches | Blocks all other (S) and (X) |
| **File Shared (S)** | Read | Reading file contents | Allows other (S); blocks (X) |
| **File Exclusive (X)** | Write | `workspace.patch` on single file | Blocks all other (S) and (X) |

---

## 3. Database Persistence Schema

```sql
CREATE TABLE IF NOT EXISTS locks (
    resource_uri TEXT PRIMARY KEY,        -- e.g. "workspace/ws-1" or "file/ws-1/src/main.py"
    holder_principal_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('SHARED', 'EXCLUSIVE')),
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY(holder_principal_id) REFERENCES principals(id)
);

CREATE INDEX IF NOT EXISTS idx_locks_expiry ON locks(expires_at);
```

---

## 4. Capability Leases

A **Lease** provides temporary, revocable authority to an agent to perform bounded actions without requiring repetitive approval prompts for every sub-operation:

```
[Agent Requests Complex Task]
              │
              v
[Human Grants Scoped Lease]
      - Principal: agent-42
      - Capability: workspace.patch
      - Scope: workspace/my-project/tests/**
      - Duration: 30 minutes
              │
              v
[Agent Executes Successive Operations]
      ├── Operation 1 (tests/test_a.py) --> ALLOWED under active lease
      ├── Operation 2 (tests/test_b.py) --> ALLOWED under active lease
      └── Operation 3 (src/app.py)      --> DENIED (outside lease resource scope)
              │
              v
[Monotonic Clock Exceeds 30 Minutes]
      └── Lease Expired: New operations immediately revert to REQUIRE_APPROVAL
```

### Lease Invariant
A lease can **never** grant authority higher than the parent policy. If Platform or User policy denies an action, a lease cannot authorize it.

```sql
CREATE TABLE IF NOT EXISTS leases (
    id TEXT PRIMARY KEY,
    principal_id TEXT NOT NULL,
    capability_name TEXT NOT NULL,
    resource_pattern TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'EXPIRED', 'REVOKED')),
    granted_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY(principal_id) REFERENCES principals(id)
);

CREATE INDEX IF NOT EXISTS idx_leases_lookup ON leases(principal_id, capability_name, status);
```

---

## 5. Stale Lock & Lease Reaper

A background task runs periodically and during `tacp doctor`:
```python
class ConcurrencyManager:
    def reap_stale_locks(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cursor = self.db.cursor()
        cursor.execute("DELETE FROM locks WHERE expires_at < ?", (now,))
        reaped_count = cursor.rowcount
        self.db.commit()
        return reaped_count
```
