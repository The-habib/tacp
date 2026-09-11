# TACP Phase 6: Runtime Hot Path Analysis & UX Latency Budgets
**Document ID:** `TACP-PERF-LAT-001`  
**Classification:** Performance Architecture & UX Specification  
**Baseline Environment:** Android 13 / Termux `aarch64` (Octa-core Cortex-A78/A55)  
**Date:** September 2026  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. UX Latency Philosophy

A security control plane must not impose an unbearable "security tax" on everyday tool interactions. Developers and autonomous AI agents will reject or bypass a system that feels sluggish.

### Critical Distinction:
- **Engineering Verification Latency (`./verify`):** Runs formatting, static typing, 689+ unit/security tests, and dependency audits. This takes ~50-70 seconds and belongs exclusively in CI or pre-commit gates.
- **Runtime Tool-Call Latency:** The wall-clock elapsed time experienced by an LLM/user when invoking a single TACP capability. This must be measured in **single-digit or low double-digit milliseconds**.

---

## 2. Latency Budget Categories

We define four explicit operational latency tiers based on Android hardware constraints:

### 2.1 Category 1: `FAST` (Read-Only Local Operations)
- **Capabilities:** `system.inspect`, `system.version`, `workspace.inspect`, `fs.stat`, `fs.list`, `fs.read`, `fs.search`, `process.list`
- **Target TACP Overhead:** $\le 3\text{ ms}$ (p50), $\le 8\text{ ms}$ (p95)
- **Expected Device Execution:** $2 - 15\text{ ms}$ (depending on file/directory size)
- **Acceptable p95 Total:** $\le 20\text{ ms}$
- **Latency Contributors:** Path resolution, jailing check, secret scanning, cached workspace lookup, audit append.

### 2.2 Category 2: `NORMAL` (Bounded Local Mutations)
- **Capabilities:** `workspace.patch`, `workspace.patch_batch` (dry-run or pre-authorized via lease)
- **Target TACP Overhead:** $\le 6\text{ ms}$ (p50), $\le 15\text{ ms}$ (p95)
- **Expected Device Execution:** $10 - 35\text{ ms}$ (file I/O, atomic temporary replace, snapshot creation)
- **Acceptable p95 Total:** $\le 50\text{ ms}$
- **Latency Contributors:** Diff parsing, pre-image hash verification, file lock acquisition, rollback snapshot storage, atomic rename, post-image verification, audit log write.

### 2.3 Category 3: `CONTROLLED` (Bounded Process Execution)
- **Capabilities:** `execution.request` (`printf`, `echo`, `true`)
- **Target TACP Overhead:** $\le 5\text{ ms}$ (p50), $\le 12\text{ ms}$ (p95)
- **Expected Subprocess Spawning & Reaping:** $8 - 25\text{ ms}$ (Android Bionic `fork`/`exec` and `setsid`)
- **Acceptable p95 Total:** $\le 40\text{ ms}$ (for short commands)
- **Latency Contributors:** 7-stage resolution, digest cache lookup, environment assembly, contract SHA-256 hash, DB execution row creation, `Popen` fork/exec, Model B stream polling, signal reap, output sanitization.

### 2.4 Category 4: `INTERACTIVE` (Human-in-the-Loop Required)
- **Capabilities:** Unleased mutations, policy-gated executions, high-risk operations
- **TACP System Overhead:** $\le 8\text{ ms}$ (ticket creation + plan generation)
- **Human Response Time:** Variable ($1 - 30\text{ seconds}$)
- **Acceptable Post-Approval Execution p95:** $\le 50\text{ ms}$
- **Key UX Principle:** The human decision time dominates; therefore, TACP must present a concise, clear plan (files affected, risk tier, byte delta) without technical noise or redundant prompts.

---

## 3. Hot-Path Stage Budgets & Instrumentation

To prevent latency regressions, TACP Phase 6 introduces internal timing metrics recorded in each audit entry and response metadata:
- `policy_ms`: Time spent in policy rules and trust-profile resolution.
- `approval_ms`: Time spent querying, validating, or consuming approval tickets/leases.
- `provider_ms`: Time spent inside the underlying filesystem or process provider.
- `audit_ms`: Time spent computing hash and persisting audit log.
- `total_ms`: End-to-end wall-clock duration of the request.

### Per-Stage Latency Budget Matrix:

| Pipeline Stage | Fast Path Budget (p95) | Mutation Budget (p95) | Execution Budget (p95) |
|---|---|---|---|
| Request Parsing & Schema | 0.2 ms | 0.5 ms | 0.5 ms |
| Principal & Context Setup | 0.1 ms | 0.1 ms | 0.1 ms |
| Workspace Resolution (Cached) | 0.2 ms | 0.3 ms | 0.3 ms |
| Policy & Trust Profile | 0.5 ms | 1.0 ms | 1.0 ms |
| Lease / Approval Consumption | N/A (0 ms) | 2.5 ms | 2.5 ms |
| Provider / Core Action | 5.0 ms | 25.0 ms | 20.0 ms |
| Output Sanitization / Checks | 0.5 ms | 1.5 ms | 1.5 ms |
| Audit Append (WAL) | 1.5 ms | 2.0 ms | 2.0 ms |
| **Total Overhead Ceiling** | **8.0 ms** | **32.9 ms** | **27.9 ms** |

---

## 4. Latency Mitigation Strategies

1. **In-Memory Workspace Cache:** Eliminates 2 redundant SQLite SELECT queries per file operation.
2. **In-Memory Previous Audit Hash Tracking:** Eliminates the `SELECT prev_hash ... LIMIT 1` query prior to appending audit records.
3. **Decoupled Verification:** `verify_integrity()` is never invoked on request hot paths; it is reserved for administrative audits.
4. **Digest Cache Keying:** `(inode, dev, mtime_ns)` eliminates re-reading multi-megabyte binaries on every execution.
