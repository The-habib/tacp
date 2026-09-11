# TACP v0.3.0-rc.1 Release Report
## Phase 2.5 — Gate C: Vertical Slice 2 (Governed Multi-File Patch Batch)

**Release Candidate:** `v0.3.0-rc.1`  
**Date:** September 11, 2026  
**Platform:** Termux on Android (Linux aarch64)  
**Status:** **READY FOR RELEASE / VERIFIED**

---

## 1. Executive Summary

TACP v0.3.0-rc.1 delivers the second governed mutating capability to the Termux AI Control Plane: **`workspace.patch_batch`**.
This capability empowers autonomous AI agents to execute coordinated, multi-file code modifications atomically across an authorized workspace root while strictly maintaining the core constitutional principle:

> **"AI may be autonomous, but AI must never be sovereign."**

Multi-file mutations are governed under all-or-nothing transactional guarantees: if any file fails in preflight validation, staging, atomic commit, or post-write checksum verification, all modified files are immediately restored to pre-batch snapshots.

---

## 2. Key Features & Architectural Invariants

### 2.1 Governed Multi-File Patch Batch (`workspace.patch_batch`)
- Atomically applies unified diff patches across up to 10 files in a single request.
- Strict item validation: subpath, diff content, and base checksum are required for each item.
- Strict aggregate bounds: max 10 files, max 1 MB cumulative patch size, max 5 MB cumulative resulting size.

### 2.2 Dual Feature Flags (Defense in Depth)
- Mutation requires `mutation_enabled = true` **AND** `batch_mutation_enabled = true`.
- Both flags default to `false` (strict read-only posture).
- The MCP tool is completely omitted from discovery unless both flags are active.

### 2.3 Deadlock-Free Lexicographical Multi-Resource Locking
- Resource locks are acquired in sorted lexicographical order (`f"{workspace_id}:{subpath}"`).
- If any lock is contested or fails to acquire, all previously acquired locks are released in reverse order.

### 2.4 Canonical Batch Hashing & Scoped Human Approval
- Deterministic canonical batch hash computed via CRLF normalization, subpath sorting, and compact JSON serialization.
- Approval tickets are cryptographically bound to the canonical batch hash, workspace, and principal, enforcing single-use replay immunity.

### 2.5 All-or-Nothing Transactional Filesystem Engine
- **Preflight:** Validates all items, simulates diffs, verifies OCC base checksums, and enforces size limits.
- **Snapshots:** Durable pre-patch backups created at `~/.tacp/snapshots/{batch_id}/`.
- **Staging:** Temporary sibling files (`.tacp_tmp_{batch_id}_{idx}_{uuid}`) created in each target file's parent directory, avoiding Android `EXDEV` cross-device errors, with explicit `fsync` persistence.
- **Commit:** Atomic `os.replace()` rename followed by post-write SHA-256 verification.
- **Rollback:** Automated emergency rollback restores snapshots if any file fails during commit.

### 2.6 Dedicated CLI & Operations Tooling
- CLI commands: `tacp batch list`, `tacp batch show <batch_id>`, and `tacp batch rollback <batch_id>`.

---

## 3. Verification & Quality Metrics

- **Total Test Suite:** 437 automated tests (100% pass rate).
- **Baseline Invariance:** 269 Phase 1.5 tests + 87 Slice 1 tests pass with 0 regressions.
- **Slice 2 Test Additions:** 81 tests added (16 failure injection matrix + 40 security attack suite + integration + MCP tests).
- **Security Attack Suite:** 40 adversarial attack cases defeated (Total: 190 automated security tests).
- **Code Coverage:** 84% statement coverage across 2,342 statements.
- **Static Analysis & Type Safety:** 0 Ruff lint errors, 0 format diffs, 0 Mypy type errors.
- **Official MCP Inspector:** Strict validation passes on `@modelcontextprotocol/inspector` v2.6.0 with 0 schema errors across 15 exposed tools.
- **Native Android Performance:**
  - 5-File Dry-Run Simulation: **5.02 ms**
  - 5-File Live Execution: **40.58 ms**
  - 5-File Rollback: **8.73 ms**

---

## 4. Deliverables & Evidence Index

- **Operator Runbook:** `docs/execution/WORKSPACE-PATCH-BATCH-RUNBOOK.md`
- **Architectural Specification:** `docs/phases/SLICE-2-MULTI-FILE-PATCH-DESIGN.md`
- **Design Review:** `docs/phases/SLICE-2-DESIGN-REVIEW.md`
- **Implementation Report:** `docs/evidence/PHASE-2-SLICE-2/IMPLEMENTATION.md`
- **Test Verification:** `docs/evidence/PHASE-2-SLICE-2/TESTS.md`
- **Security Report:** `docs/evidence/PHASE-2-SLICE-2/SECURITY.md`
- **MCP Protocol Report:** `docs/evidence/PHASE-2-SLICE-2/MCP.md`
- **Device Mechanics Report:** `docs/evidence/PHASE-2-SLICE-2/DEVICE.md`
- **Performance Benchmarks:** `docs/evidence/PHASE-2-SLICE-2/PERFORMANCE.md`
- **Independent Compliance Review:** `docs/evidence/PHASE-2-SLICE-2/REVIEW.md`
- **Release Gate Evaluation:** `docs/evidence/PHASE-2-SLICE-2/RELEASE-GATE.md`

---

## 5. Formal Verdict

Vertical Slice 2 satisfies all architectural directives, security invariants, and operational standards mandated for TACP Phase 2.5.

**TACP Phase 2.5 Gate C is formally signed off: PASSED.**
