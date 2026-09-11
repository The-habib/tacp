# TACP Phase 3 — Current State Audit & Execution Core Hardening
## Pre-Shell / Pre-Android / Pre-Network Security Gate

- **Date:** September 11, 2026
- **Current Reported Release:** `v0.3.0-rc.1`
- **Current Commit:** `2f8d08b`
- **Platform:** Termux on Android (Linux 5.15.197 aarch64, Python 3.14.6)
- **Status:** **AUDITED — DEFECTS & HARDENING PRIORITIES IDENTIFIED**

---

## 1. Executive Summary

This audit establishes the empirical baseline for **Phase 3: Execution Core Hardening**.
Before introducing high-power capabilities (such as command execution, process control, or network integration), TACP's governance, authorization, concurrency, protocol conformance, and release architecture must be hardened into an authoritative, defect-free foundation.

**Constitutional Mandate:**
> **"Power must never outpace control."**

The previous Phase 2 reports asserted strong milestones (437 automated tests, 190 security cases, 84% coverage, official MCP Inspector validation). While these achievements are real and functional, our independent code audit has uncovered critical architectural, security, and consistency gaps that must be corrected.

---

## 2. Investigation & Findings on the 12 Observed Invariants

### Finding 1: Release Metadata Inconsistency
- **Observation:** Git tag `v0.3.0-rc.1` was created, yet `pyproject.toml` remained at `version = "0.1.0rc1"`, `src/tacp/__init__.py` remained at `__version__ = "0.1.0-rc.1"`, and `SystemService.get_version()` hardcoded `"0.1.0-rc.1"`. Multiple integration and unit tests asserted `"0.1.0-rc.1"` because they were frozen against Phase 1 values.
- **Root Cause:** Versioning lacked a single authoritative source of truth. Feature additions in Slices 1 and 2 updated release tags and documentation without propagating to runtime metadata.
- **Remediation Plan:** Establish `src/tacp/__init__.py` and `pyproject.toml` as the unified source of truth. Parameterize runtime services and tests to reference `tacp.__version__`. Add `VERSION-CONSISTENCY-TEST` ensuring package, runtime, CLI, and release metadata never diverge.

### Finding 2: GitHub Actions CI Verification Completeness Gap
- **Observation:** Local `./verify` executes 7 rigorous stages (ShellCheck, Ruff format, Ruff check, Mypy, unit/integration/device tests with coverage, security tests, and pip-audit). In contrast, GitHub Actions `.github/workflows/ci.yml` only executed `tests/unit`, and `.github/workflows/security.yml` only executed `tests/security`.
- **Impact:** Integration tests (`test_workspace_patch.py`, `test_workspace_patch_batch.py`, `test_mcp_patch_batch.py`), failure injection tests (`test_slice2_failure_injection.py`), and CLI contract tests were never executed in GitHub CI!
- **Remediation Plan:** Redesign `.github/workflows/ci.yml` to mirror all canonical local verification gates. Explicitly tag host-dependent hardware checks as `DEVICE-ONLY` so GitHub CI does not claim false verification.

### Finding 3: uv.lock Enforcement Gap in CI
- **Observation:** GitHub Actions workflows ran `uv pip install -e ".[dev]"`, which resolves dependencies dynamically at run-time rather than enforcing the committed `uv.lock`.
- **Impact:** Upstream dependency releases could introduce breaking changes or untracked vulnerabilities without failing lock validation.
- **Remediation Plan:** Replace `uv pip install` with `uv sync --locked` (or `uv run --locked`). Add an automated consistency test verifying that `pyproject.toml` and `uv.lock` match.

### Finding 4: GitHub Actions Mutable Tag Usage
- **Observation:** Both `ci.yml` and `security.yml` referenced mutable action tags: `actions/checkout@v4`, `actions/setup-python@v5`, `astral-sh/setup-uv@v5`.
- **Impact:** Mutable tags can be maliciously retargeted or mutated upstream, violating supply-chain integrity standards (SLSA Level 3).
- **Remediation Plan:** Pin all GitHub Actions to immutable full 40-character commit SHAs with inline comments documenting upstream release versions.

### Finding 5: MCP Protocol Layer Conformance Review
- **Observation:** `src/tacp/access/mcp/protocol.py` implements a custom JSON-RPC 2.0 parser and handler. While validated by `@modelcontextprotocol/inspector`, the implementation manually handles error mapping, notification routing, and protocol version negotiation.
- **Impact:** Divergence risks on edge cases (e.g. malformed JSON-RPC batches, unstructured errors, `_meta` handling).
- **Remediation Plan:** Conduct a complete conformance audit against the official MCP 2026-07-28 specification using official inspector logs. Standardize protocol vs. application error structures. Evaluate official Python SDK integration tradeoffs.

### Finding 6: Minimal Principal & Identity Model
- **Observation:** `src/tacp/control/identity.py` defines a bare 17-line `Principal` dataclass (`id="anonymous"`, `role="agent"`, `authenticated=False`).
- **Impact:** In local stdio mode, callers are implicitly treated as trusted local agents with no distinction between trust tiers, caller sources, or authentication proofs.
- **Remediation Plan:** Enrich `Principal` to distinguish ID, type (AGENT, HUMAN, SYSTEM), role, trust tier (UNTRUSTED, RESTRICTED, PRIVILEGED), authentication state, and credential source. Ensure caller-supplied headers/arguments never elevate privilege without cryptographic verification.

### Finding 7: Approval Token Plaintext Storage & Cryptographic Overstatement
- **Observation:** In `src/tacp/control/approval.py`, bearer tokens (`tacp_appr_<hex>`) are generated via `secrets.token_hex(16)` and stored in plaintext in the `approvals.token` column. Phase 2 documentation referred to tickets as "cryptographically locked".
- **Impact:** The phrase "cryptographically locked" was technically overstated: while the batch content is cryptographically hashed (SHA-256), the bearer token itself was stored unhashed in SQLite. A read-only SQL injection or unauthorized database read would compromise valid approval tokens.
- **Remediation Plan:** Store only `token_hash = sha256(token)` in the database. Look up tickets by hashing the bearer token at verification time. Accurately describe the cryptographic boundaries in documentation.

### Finding 8: LockService Check-Then-Write Concurrency Vulnerability (TOCTOU)
- **Observation:** `LockService.acquire_lock` performed:
  1. `SELECT ... FROM locks WHERE resource_id = ?`
  2. In-memory expiration check
  3. `INSERT OR REPLACE INTO locks ...`
- **Impact:** Two concurrent processes could both execute the `SELECT` query, both find no active lock, and both execute `INSERT OR REPLACE`. Process B would clobber Process A's lock, leaving both callers believing they hold exclusive resource access.
- **Remediation Plan:** Replace non-atomic check-then-write with an atomic transaction using SQLite `BEGIN IMMEDIATE`, atomic expired lock purging, and atomic `INSERT` guarded by `PRIMARY KEY (resource_id)` with conflict detection. Add multi-threaded and multi-process concurrency tests.

### Finding 9: Rollback Lacking Explicit Capability Governance
- **Observation:** `PatchService.rollback_patch` and `rollback_batch` modified filesystem state using pre-mutation snapshots without routing through `PolicyEngine.evaluate_request`.
- **Impact:** Any caller with CLI or internal service access could trigger a rollback without policy validation, risking unauthorized state reversion.
- **Remediation Plan:** Formulate rollback as an explicit mutating capability (`workspace.rollback` / `workspace.batch_rollback`) subject to policy checks, principal authorization, and audit logging.

### Finding 10: Duplication Between MCP Registry and PatchService
- **Observation:** `McpToolRegistry.execute_tool` performed policy checks, approval ticket creation, and audit logging for `workspace.patch` and `workspace.patch_batch`. Then, inside `PatchService.execute_patch` and `execute_patch_batch`, the exact same policy checks, ticket creation, and audit logging were executed again!
- **Impact:** Redundant database writes, duplicate audit events, risk of divergence if policy logic changes in one place but not the other.
- **Remediation Plan:** Establish ONE authoritative application governance pipeline: MCP Adapter $\to$ Application Service $\to$ Policy Engine / Control Pipeline $\to$ Filesystem Provider. The MCP layer must remain a thin adapter that passes request context to the domain service.

### Finding 11: Unified-Diff Parser Security & Edge Cases
- **Observation:** `FilesystemProvider._apply_unified_diff` skipped unrecognized lines inside a hunk without raising an error (`elif line.startswith("\\"): pass; i += 1`). Header parsing did not enforce strict hunk count consistency.
- **Impact:** Malformed or adversarial diffs containing invalid syntax could silently drop modifications or produce unexpected file contents.
- **Remediation Plan:** Implement strict syntax validation in `_apply_unified_diff`. Reject unrecognized line prefixes with `TacpValidationError`. Validate that line additions and removals match hunk header numbers. Add an exhaustive parser test suite (CRLF, Unicode, zero-count hunks, empty files, multi-hunk replacements).

### Finding 12: Rollback Characterization Accuracy
- **Observation:** Previous documentation described multi-file rollback as a "filesystem transaction".
- **Impact:** Mischaracterizes the underlying OS reality. POSIX filesystems (ext4, f2fs) do not support multi-file transactions. TACP provides an application-level, snapshot-backed two-phase commit protocol with durable `fsync` and crash recovery, not a kernel VFS transaction.
- **Remediation Plan:** Correct documentation across runbooks, architecture specs, and evidence files to accurately describe the mechanism as "application-level snapshot-backed two-phase commit".

---

## 3. Codebase Inventory & Current Health

- **Source Code:** 74 Python modules across `src/tacp/` (clean architecture: domain, control, core, infrastructure, providers, access, cli).
- **Test Suite:** 437 automated tests passing in 28.75s.
- **Static Analysis:** 0 Ruff lint errors, 0 format diffs, 0 Mypy type errors across all modules and tests.
- **Security Baseline:** 190 automated security tests defeating path traversal, secret patterns, symlink escapes, replay attacks, and failure injection scenarios.

---

## 4. Phase 3 Engineering Execution Sequence

1. **Section 4:** Authoritative Versioning Architecture & `VERSION-CONSISTENCY-TEST`.
2. **Sections 5–9:** CI Redesign, `uv.lock` Enforcement, Action SHA Pinning, and Governance Gap Analysis.
3. **Sections 10–11:** MCP 2026-07-28 Conformance Audit & Python SDK Evaluation.
4. **Sections 12–13:** Principal & Identity Model Hardening.
5. **Sections 14–16:** Approval Security & Token Hashing.
6. **Sections 17–19:** Concurrency-Safe Atomic Lock Service.
7. **Section 20:** Rollback Governance & Authorization.
8. **Sections 21–22:** Unified Governance Pipeline & Traceable Request Context.
9. **Sections 23–25:** Unified-Diff Parser Hardening & Differential Testing.
10. **Sections 26–35:** Metadata Preservation, Snapshot Integrity, Database/Audit Hardening, Secret Redaction.
11. **Sections 36–45:** Concurrency Race Tests, Mutation Sabotage, Device Benchmarks, Clean-Room Verification.
12. **Sections 46–52:** Release Identity Update (`v0.3.1-rc.1`), Evidence Generation, Independent Review.
13. **Sections 53–55:** Controlled Command Execution Design (`docs/execution/COMMAND-EXECUTION-DESIGN.md`) & OpenAI Tunnel Readiness.
14. **Sections 56–57:** Final Hardening Report & Safe Stop.
