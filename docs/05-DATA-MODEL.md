# TACP Data Model & State Storage

**Status**: SKELETON / PLANNED  
**Target Phase**: Phase 2  

---

## 1. State Store Requirements

TACP requires structured, durable, and crash-resilient local persistence for:
1. **Registered Workspaces**: Approved paths, access levels, and metadata.
2. **Capability Leases**: Temporary, revocable permissions granted to agents.
3. **Audit Log**: Append-only log of all actions, inputs, decisions, and outcomes.

---

## 2. Proposed Persistence Technologies

- **SQLite (WAL mode)**: Embedded, lightweight, native in Python standard library, Zero external dependencies.
- **JSON Lines**: Tamper-evident, streamable audit logging.

---

## 3. Schema Definitions [PLANNED]

```sql
-- Workspace Entity (Planned)
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    root_path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL
);

-- Audit Log Entity (Planned)
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    session_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    plane TEXT NOT NULL,
    action TEXT NOT NULL,
    parameters_redacted TEXT NOT NULL,
    policy_decision TEXT NOT NULL,
    outcome TEXT NOT NULL,
    duration_ms INTEGER NOT NULL
);
```
