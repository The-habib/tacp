# TACP Phase 2 Gate B — Slice 1 Current State Audit & Implementation Plan

**Document:** `docs/phases/GATE-B-SLICE-1-CURRENT-STATE.md`  
**Phase:** Phase 2 Gate B — Vertical Slice 1 (Governed Workspace Patch)  
**Lead Engineer:** Antigravity Principal Systems Architect & Security Engineer  
**Baseline Git Commit:** `7930a45`  
**Baseline Test Verification:** 269 passed (0 failures, 82% coverage)  
**Date:** September 11, 2026  

---

## 1. Executive Summary

Before introducing any mutation code into the repository, this audit identifies which existing components from TACP 0.1 can be directly reused, what components must be created, potential conflicts, required database migrations, and the exact step-by-step implementation sequence.

The core objective of Vertical Slice 1 is to implement **`workspace.patch`** exclusively for single text files inside an authorized workspace, with full policy enforcement, risk assessment, human approval verification, single-file backup, base checksum conflict detection, atomic replacement (`os.replace`), post-verification, and cryptographic audit logging.

---

## 2. Component Analysis

### 2.1 Reusable Components (from TACP 0.1 Baseline)
1. **Path Jailing (`src/tacp/providers/filesystem.py:38-100`)**:
   - `_resolve_in_jail(workspace_root, subpath)`: Canonical realpath resolution, 4096-char guard, null-byte rejection, percent-encoding rejection, absolute path escape rejection, and `relative_to` containment check.
   - Reused directly for target file resolution and parent directory confinement.
2. **Secret File & Pattern Classification (`src/tacp/providers/filesystem.py:14-30`)**:
   - `SECRET_EXTENSIONS`, `SECRET_FILENAMES`, `SECRET_PATTERNS`.
   - Reused directly to reject patch proposals targeting `.env`, `id_rsa`, etc.
3. **Secret Redaction Engine (`src/tacp/infrastructure/logging.py`)**:
   - `redact_string`, `redact_dict`.
   - Reused directly for patch error sanitization and audit log parameter scrubbing.
4. **Audit Service & Cryptographic Hash-Chaining (`src/tacp/core/audit_service.py`)**:
   - `AuditService.record_event()` and `verify_integrity()`.
   - Reused to record all mutation attempts (`APPLIED`, `SIMULATED`, `CONFLICT`, `DENIED`, `FAILED`, `ROLLED_BACK`) into SQLite and JSONL with SHA-256 hash chaining.
5. **Database Manager & Migration Runner (`src/tacp/infrastructure/database.py`, `migrations.py`)**:
   - SQLite WAL mode connection management and versioned `schema_migrations`.
   - Reused to execute Migration 2 for Slice 1 entities.
6. **Workspace Service (`src/tacp/core/workspace_service.py`)**:
   - `get_workspace`, `list_workspaces`, workspace active status check.
   - Reused to resolve target workspace and verify root path existence.
7. **MCP Protocol Server & Dispatcher (`src/tacp/access/mcp/`)**:
   - Dual-protocol framing (`2026-07-28` and `2024-11-05`), JSON-RPC parsing, error serialization.
   - Reused to register and dispatch `tacp_workspace_patch`.

### 2.2 Missing Components (Required for Slice 1)
1. **Mutation Feature Flag (`src/tacp/infrastructure/config.py`)**:
   - Need `mutation_enabled: bool = False` by default.
   - Need patch limits in `OutputLimits`: `max_patch_bytes = 262144` (256 KB), `max_file_size_bytes = 1048576` (1 MB).
2. **Database Migration 2 (`src/tacp/infrastructure/migrations.py`)**:
   - Tables: `principals`, `policies`, `approvals`, `patches`, `locks`.
3. **Domain Models (`src/tacp/domain/`)**:
   - `WorkspacePatch`, `PatchResult`, `PatchStatus` in `domain/patch.py`.
   - `ExecutionContract` in `domain/contract.py`.
   - Expanded `ErrorCode` in `domain/errors.py` (`MUTATION_DISABLED`, `APPROVAL_REQUIRED`, `APPROVAL_EXPIRED`, `APPROVAL_ALREADY_USED`, `CONFLICT`, `UNSUPPORTED_FILE`, `PATCH_INVALID`, `CHECKPOINT_FAILED`, `MUTATION_FAILED`, `ROLLBACK_FAILED`, `LOCK_CONFLICT`, `LOCK_EXPIRED`).
4. **Control Plane Engines (`src/tacp/control/`)**:
   - `PolicyEngine` upgrade: Evaluate 5-tier policy, check `mutation_enabled`, return `ALLOW`, `DENY`, or `REQUIRE_APPROVAL`.
   - `ApprovalEngine` (`src/tacp/control/approval.py`): Query active tickets, check expiration, verify resource scope, enforce single-use consumption.
   - `RiskEngine` upgrade: Map `workspace.patch` to `R2` (or `R1` for dry-run).
5. **Lock Service (`src/tacp/core/lock_service.py`)**:
   - Single-file lock acquisition, holding verification, TTL expiry, and release.
6. **Atomic Mutation & Diff Engine (`src/tacp/providers/filesystem.py`)**:
   - `apply_patch(target_path, patch_diff, base_checksum, dry_run) -> PatchResult`:
     - Verification of text encoding (UTF-8) and binary rejection.
     - Single-file backup creation in `~/.tacp/snapshots/{patch_id}/`.
     - Base checksum verification against current file bytes.
     - Unified diff application.
     - Atomic replacement via `.tacp_tmp_{uuid}` in same parent directory (`os.fsync` + `os.replace`).
     - Post-write checksum verification with automatic rollback from backup if failed.
7. **Core Patch Service (`src/tacp/core/patch_service.py`)**:
   - Orchestrates the 16-stage pipeline for `workspace.patch`.
8. **MCP Tool Integration (`src/tacp/access/mcp/tools.py`)**:
   - Expose `tacp_workspace_patch` adhering to MCP 2026-07-28 tool gate.

---

## 3. Potential Conflicts & Mitigations

1. **Conflict**: `PolicyEngine` currently has a hardcoded static set `ALLOWED_CAPABILITIES`.
   - *Mitigation*: Dynamically check `mutation_enabled`. If `mutation_enabled=True`, include `workspace.patch` in evaluated capabilities; otherwise return `PolicyDecision(allowed=False, reason="Mutation is disabled (read-only mode active)")`.
2. **Conflict**: `CapabilityService.READONLY_CAPABILITIES` is static.
   - *Mitigation*: Separate read-only capabilities from mutating capabilities. Only register `workspace.patch` in `list_capabilities()` / `list_raw()` if mutation is enabled or clearly flag `is_mutating=True`.
3. **Conflict**: Existing tests assume `read_only=True` is permanent.
   - *Mitigation*: Default configuration remains `mutation_enabled=False`. All 269 existing tests run in default mode and remain 100% unaffected. Mutation tests explicitly instantiate config or pass context with `mutation_enabled=True`.

---

## 4. Implementation Sequence (Vertical Slice 1)

```
[Step 1: Domain & Errors]
  ├── Update src/tacp/domain/errors.py with new ErrorCodes
  ├── Create src/tacp/domain/patch.py (WorkspacePatch, PatchResult, PatchStatus)
  └── Create src/tacp/domain/contract.py (ExecutionContract)

[Step 2: Configuration & Feature Flag]
  └── Update src/tacp/infrastructure/config.py (mutation_enabled, patch limits)

[Step 3: Database Migration 2]
  └── Add Migration 2 in src/tacp/infrastructure/migrations.py (principals, policies, approvals, patches, locks)

[Step 4: Control Plane Engines]
  ├── Update src/tacp/control/policy.py (5-tier evaluation, mutation flag check)
  ├── Update src/tacp/control/risk.py (R0-R5 risk scoring, L0-L5 autonomy)
  ├── Create src/tacp/control/approval.py (ApprovalEngine, ticket consumption)
  └── Create src/tacp/core/lock_service.py (LockService, TTL, conflict)

[Step 5: Provider Atomic Mutation]
  └── Implement apply_patch & backup in src/tacp/providers/filesystem.py

[Step 6: Core Patch Service & Pipeline]
  └── Create src/tacp/core/patch_service.py (16-stage pipeline coordination)

[Step 7: MCP Tool Registration]
  ├── Register capability in src/tacp/core/capability_service.py
  └── Add tacp_workspace_patch in src/tacp/access/mcp/tools.py

[Step 8: Testing & Verification]
  ├── Run existing read-only regression suite (269 tests)
  ├── Add 80+ new behavioral tests (Domain, Path, Patch, Policy, Approval, Locking, Atomicity, Audit, MCP)
  ├── Run 30 security regression tests
  ├── Run sabotage failure injection
  ├── Run MCP Inspector validation
  └── Execute ./verify (all stages)
```
