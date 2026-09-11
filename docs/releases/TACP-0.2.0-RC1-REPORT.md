# TACP v0.2.0-rc.1 Release Report
## Phase 2 — Gate B: Vertical Slice 1 (Governed Workspace Patch)

**Release Candidate:** `v0.2.0-rc.1`  
**Date:** September 11, 2026  
**Platform:** Termux on Android (Linux aarch64)  
**Status:** **READY FOR RELEASE / VERIFIED**

---

## 1. Executive Summary

TACP v0.2.0-rc.1 marks the introduction of the first governed mutating capability in the Termux AI Control Plane: **`workspace.patch`**.
This release transitions TACP from a purely read-only observer to a secure, auditable, human-supervised code modification platform.

### Constitutional Principle:
> **"AI may be autonomous, but AI must never be sovereign."**

Under this mandate, autonomous agents cannot directly edit, overwrite, or delete files. Every patch must traverse an uncompromising **16-stage pipeline** requiring optimistic concurrency control, resource locking, risk evaluation, and explicit human approval.

---

## 2. Key Features & Architectural Capabilities

### 2.1 Governed Workspace Patch (`workspace.patch`)
- Applies unified diff format patches to existing text files within registered workspaces.
- Strict input validation: UTF-8 only, null-byte rejection, binary detection, path jail enforcement.
- Strict boundary limits: max 256 KB diff, max 1 MB target, max 2 MB resulting file.

### 2.2 16-Stage Governance Pipeline
Enforces full end-to-end policy, authentication, risk rating, locking, and execution contract before any file modification occurs.

### 2.3 Optimistic Concurrency Control (OCC)
- Requires callers to specify `base_checksum` (SHA-256) of the target file.
- Guarantees that stale diffs cannot overwrite concurrent edits.

### 2.4 Human Approval Engine
- Mutating operations in live mode require human approval.
- Emits cryptographically secure tickets bound across 5 dimensions: `principal`, `action`, `workspace`, `target_path`, and `patch_hash`.
- Atomic single-use consumption prevents all replay attacks.

### 2.5 Android-Safe Atomic File Replacement
- Creates temporary sibling files (`.tacp_tmp_{uuid}`) in the **same parent directory** to completely eliminate Android cross-device `EXDEV` link errors.
- Enforces physical persistence via `os.fsync()` before executing atomic POSIX `os.replace()`.

### 2.6 Automatic Snapshots & Instant Rollback
- Pre-mutation snapshots archived at `~/.tacp/snapshots/{patch_id}/`.
- One-step rollback command with OCC checksum guards.

---

## 3. Verification & Quality Metrics

- **Total Test Suite:** 356 automated tests (100% passing).
- **Baseline Invariance:** 269 Phase 1.5 tests pass with 0 regressions.
- **Slice 1 Test Additions:** 87 tests added (exceeds requirement of $\ge 80$).
- **Security Attack Suite:** 30 adversarial attack cases defeated (Total: 108 security test cases).
- **Code Coverage:** 89% statement coverage across 1,829 statements.
- **Type Safety & Style:** 0 Mypy type errors (40 source files), 0 Ruff lint errors, 100% formatted.
- **Device Performance (on Android host):**
  - Dry-run simulation latency: **2.33 ms**
  - Live patch end-to-end latency: **34.70 ms**
  - Rollback latency: **3.35 ms**

---

## 4. Documentation & Artifact Deliverables

- **Operator Runbook:** `docs/execution/WORKSPACE-PATCH-RUNBOOK.md`
- **Implementation Report:** `docs/evidence/PHASE-2-SLICE-1/IMPLEMENTATION.md`
- **Test Verification:** `docs/evidence/PHASE-2-SLICE-1/TESTS.md`
- **Security Report:** `docs/evidence/PHASE-2-SLICE-1/SECURITY.md`
- **MCP Protocol Report:** `docs/evidence/PHASE-2-SLICE-1/MCP.md`
- **Device Mechanics Report:** `docs/evidence/PHASE-2-SLICE-1/DEVICE.md`
- **Performance Benchmarks:** `docs/evidence/PHASE-2-SLICE-1/PERFORMANCE.md`
- **Adversarial Review:** `docs/evidence/PHASE-2-SLICE-1/REVIEW.md`
- **Release Gate Evaluation:** `docs/evidence/PHASE-2-SLICE-1/RELEASE-GATE.md`

---

## 5. Next Steps

Vertical Slice 1 is complete and signed off.
Do NOT proceed to Vertical Slice 2 without explicit operator authorization.
