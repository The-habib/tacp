# TACP Phase 6: Current State Audit & Runtime Hot-Path Inventory
**Document ID:** `TACP-AUDIT-P6-001`  
**Classification:** Architecture & Performance Audit  
**Baseline Version:** v0.4.0-rc.2 (Commit: `401c19c`)  
**Target Environment:** Android 13 / Termux `aarch64`  
**Date:** September 2026  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Scope & Objectives

Phase 6 addresses the product architecture and user experience of TACP. Security must not create approval fatigue or impose unnecessary runtime latency. The objective is to make TACP **fast, low-friction, risk-adaptive, and predictable** while maintaining strict security guarantees.

This document performs an empirical audit of the existing runtime services, database queries, caching strategies, and synchronous checks.

---

## 2. Audit Answers to Key Architectural Questions

### 2.1 What currently executes for every read-only request? (e.g. `fs.read`, `fs.list`, `fs.stat`)
1. **Tool Name Normalization & Capability Lookup:** `McpToolRegistry.normalize_tool_name` followed by in-memory `capability_service.get_capability()`.
2. **Context & Principal Instantiation:** `RequestContext` created with `Principal.local_agent("mcp-client")`.
3. **Redundant Workspace Resolution:**
   - `McpToolRegistry.execute_tool` executes `workspace_service.get_workspace(workspace_id)` -> **SQLite query #1**.
   - Deserializes `metadata_json`.
4. **Policy Engine Evaluation:** `policy_engine.evaluate_request()` verifies capability is enabled and workspace is active.
5. **Secondary Workspace Resolution in Dispatch:**
   - Dispatches to `filesystem_service.read_file()`.
   - `filesystem_service` executes `workspace_service.get_workspace(workspace_id)` **a second time** -> **SQLite query #2**.
6. **Path Resolution & Jailing:** `FilesystemProvider.resolve_safe_path()` checks `Path.resolve().is_relative_to(workspace_root)`.
7. **Restricted Path & Secret Check:** Scans path against sensitive regexes (`.git/hooks`, private keys).
8. **File Classification & Read:** Reads up to `max_file_size_bytes` (1MB cap) and checks for binary null bytes.
9. **Audit Trail Recording:**
   - Queries `audit_logs` for `prev_hash` -> **SQLite query #3**.
   - Computes canonical SHA-256 JSON hash of event.
   - Inserts audit event into `audit_logs` -> **SQLite write query #4**.

**Key Finding:** A single `fs.read` executes **3 SQLite SELECTs and 1 SQLite INSERT**, with duplicate workspace lookups.

---

### 2.2 What currently executes for every mutation? (`workspace.patch`, `workspace.patch_batch`)
1. **Dispatch Bypass:** Mutating calls bypass MCP generic policy check and dispatch directly to `patch_service`.
2. **Diff Parsing & Path Resolution:** Unified diff is parsed; target paths are checked against workspace root.
3. **Pre-image Checksum Verification:** Reads target file on disk and verifies SHA-256 baseline checksum.
4. **Policy Evaluation:** `policy_engine.evaluate_request()` verifies mutation is enabled and checks trust tier.
5. **Approval Enforcement:**
   - Reads `approval_token` from arguments.
   - Queries `approvals` table for ticket -> **SQLite query**.
   - Validates 5-dimensional scope (principal, action, workspace, target_path, patch_hash).
   - Atomic conditional SQL update sets status `CONSUMED` -> **SQLite write**.
6. **File Locking:** `lock_service.acquire_lock()` creates lock record in SQLite or memory.
7. **Snapshot & Backup Creation:** Copies pre-image content into rollback snapshot table.
8. **Atomic Diff Application:** Writes patched content to temporary file, syncs, and performs atomic `os.replace`.
9. **Post-image Verification:** Re-reads patched file, computes post-image SHA-256 hash.
10. **Audit Recording:** Appends audit entry with prev_hash chain -> **SQLite write**.
11. **Lock Release:** Releases lock.

---

### 2.3 What currently executes for every command execution? (`execution.request`)
1. **Workspace Root Resolution:** Queries `workspaces` table -> **SQLite query**.
2. **7-Stage Executable Resolution:**
   - Verifies entry point is in `SAFE_SEARCH_PATHS`.
   - Resolves symlinks and verifies target is inside `SAFE_SEARCH_PATHS`.
   - Verifies target basename is in `PERMITTED_EXECUTABLE_NAMES` or `TRUSTED_MULTICALL_BINARIES`.
   - Checks file permissions (fails if world-writable).
   - Inode & mtime stat; checks `_DIGEST_CACHE`. If miss, reads binary to compute SHA-256.
3. **Working Directory Jail:** Resolves CWD within workspace root.
4. **Argv Bounds & Null-Byte Validation:** Verifies argv count, arg length, checks `\x00`.
5. **Safe Environment Assembly:** Curates minimal `PATH`, injects `HOME`/`PWD`/`TMPDIR`, strips forbidden patterns and filters caller variables against allowlist.
6. **Canonical Execution Contract & Hashing:** Builds `ExecutionContract` dataclass and computes canonical SHA-256 hash.
7. **Policy Evaluation:** Checks execution capability and operator approval requirements.
8. **Dry Run Short-Circuit:** If `dry_run=True`, returns plan immediately without process spawn or approval check.
9. **Approval Consumption:** If live, consumes approval ticket matching exact contract hash.
10. **Execution Record Creation:** Inserts row into `executions` table with status `RUNNING` -> **SQLite write**.
11. **Subprocess Spawn:** `subprocess.Popen` with `preexec_fn=os.setsid`, `close_fds=True`, `shell=False`.
12. **Active Process Tracking:** Registers PID, PGID, and start_time in `_ACTIVE_PROCESSES` registry.
13. **Model B Stream Polling:** Polls stdout/stderr with byte limits. Immediately kills process group on overflow.
14. **Process Reap & Unregister:** Reaps process exit code, unregisters from `_ACTIVE_PROCESSES`.
15. **Output Sanitization:** Strips ANSI escape sequences, replaces null bytes, normalizes newlines.
16. **Execution Record Update:** Updates execution row in SQLite -> **SQLite write**.
17. **Audit Log Recording:** Inserts event in `audit_logs` -> **SQLite write**.

---

### 2.4 Which checks are cached?
- **Executable SHA-256 Digest:** Cached in `_DIGEST_CACHE` keyed by `(inode, device, mtime_ns)` in `ExecutionResolver`.
- **Nothing else is cached:** Workspace metadata, capability schemas, policy decisions, and approval tickets are queried directly from SQLite on every call.

---

### 2.5 Which checks are repeated unnecessarily?
1. **Workspace Lookup:** Called twice per filesystem operation (once in `McpToolRegistry.execute_tool`, once in `FilesystemService`).
2. **Capability Schema Listing:** Re-scanned and re-filtered on every `tools/list` RPC call.
3. **Audit Chain Previous Hash Lookup:** `SELECT prev_hash, entry_hash FROM audit_logs ORDER BY rowid DESC LIMIT 1` executed synchronously on every event.
4. **Path Canonicalization:** `workspace_root.resolve()` evaluated repeatedly inside provider methods.

---

### 2.6 Which checks are expensive?
1. **Synchronous Disk I/O & SQLite Transactions:** Multiple SQLite round trips per tool call introduce 2-5 ms latency per transaction on mobile flash storage.
2. **Directory Tree Traversal in `workspace.inspect`:** `root.rglob("*")` can take hundreds of milliseconds on large repositories.
3. **Full Audit Chain Integrity Verification:** `verify_integrity()` scans every historical event; if mistakenly run on the hot path, it scales with $O(N)$ historical events.

---

### 2.7 Which checks can safely run in parallel?
1. **Diagnostics & Read Metadata:** In multi-file or multi-resource operations, metadata inspection and stat calls can be gathered concurrently.
2. **Non-blocking Audit Ingestion:** While audit recording must be durable, batching audit writes or using SQLite WAL concurrency eliminates writer thread blocking.

---

### 2.8 Which checks genuinely require synchronous enforcement?
1. **Path Traversal & Jailing:** Must run synchronously before any filesystem access.
2. **Executable Allowlist & Symlink Verification:** Must run synchronously before `Popen`.
3. **Approval Ticket Validation & Atomic Consumption:** Must run synchronously before mutation or execution.
4. **File Locking:** Must run synchronously before file mutation.
5. **Model B Byte Ceilings:** Must run synchronously during stream capture to prevent OOM.

---

### 2.9 Which checks belong only in CI/release workflows?
1. **Full Test Suite (`pytest`):** Belongs exclusively to `./verify` and developer testing.
2. **Dependency Audit (`pip-audit`):** Belongs in CI/release gates.
3. **Full Audit Chain Verification (`verify_integrity`):** Belongs in administrative diagnostics (`audit.verify_integrity`) or background health checks, NOT in the per-request hot path.
4. **Static Analysis & Linting (`ruff`, `mypy`, `shellcheck`):** CI/developer gate only.

---

## 3. Summary of Architectural Bottlenecks & Phase 6 Solutions

| Bottleneck Identified | Architectural Impact | Phase 6 Remediation |
|---|---|---|
| Double workspace lookup | Unnecessary SQLite query overhead | In-memory `WorkspaceMetadataCache` with register/delete invalidation |
| Uncached capability list | Redundant capability formatting on `tools/list` | Cached tool definitions per `TrustProfile` |
| Approval on all mutations | Approval fatigue on minor workspace tweaks | Risk ladder (R0-R5) + capability lease model for bounded R1/R2 |
| Monolithic approval ticket | One ticket per file creates friction | Plan-first grouped approval (`ApprovalGroup`) |
| Synchronous audit SELECT | Overhead before every audit append | Track in-memory `latest_audit_hash` in `AuditService` |
| Uninformative tool errors | AI struggles to self-correct | Structured, actionable tool descriptions and error payloads |
