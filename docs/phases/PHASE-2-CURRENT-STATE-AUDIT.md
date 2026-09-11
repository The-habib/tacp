# TACP Phase 2 — Current State Reconnaissance Audit

**Document:** `docs/phases/PHASE-2-CURRENT-STATE-AUDIT.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A)  
**Auditor:** Antigravity Lead Architect, Security Engineer & QA Lead  
**Target Release Baseline:** `v0.1.0-rc.1` (Commit `a9ad2f1`)  
**Date:** September 11, 2026  

---

## 1. Executive Summary

In accordance with Phase 2 Master Engineering Specification Part I, a comprehensive reconnaissance audit of the active TACP repository (`v0.1.0-rc.1`) was conducted prior to writing any design or execution code. 

The audit evaluated all existing documentation, source code modules, dependency trees, database schemas, test harnesses, CI workflows, and platform integration points against the 86 architectural requirements of Phase 2.

**Key Finding:** While TACP 0.1 provides a verified, robust, strictly read-only inspection baseline with 269 passing automated tests and 78 security baseline cases, its internal abstractions are currently tightly optimized for read-only inspection. Governed execution requires establishing new first-class domain entities (Principals, Policies, Approvals, Leases, Locks, Execution Contracts, Jobs, and Snapshots) before any mutation or command execution capabilities can be safely introduced.

---

## 2. Architectural Claims vs. Actual Implementation

### Dimension 1: Architectural Planes & Dependency Flow
- **CLAIM**: The system implements a six-plane downward dependency architecture (Access, Intelligence, Control, Execution, Provider, Platform) where higher planes never invoke lower planes directly.
- **ACTUAL IMPLEMENTATION**:
  - `src/tacp/access/`: Contains MCP stdio server and JSON-RPC dispatchers (`server.py`, `protocol.py`, `tools.py`).
  - `src/tacp/control/`: Contains minimal `identity.py`, `policy.py`, and `risk.py`.
  - `src/tacp/core/`: Contains services (`filesystem_service.py`, `process_service.py`, `workspace_service.py`, `audit_service.py`).
  - `src/tacp/providers/`: Contains concrete providers (`filesystem.py`, `process.py`, `system.py`).
  - `src/tacp/cli/`: CLI dispatcher (`main.py`).
- **EVIDENCE**: `src/tacp/access/mcp/tools.py` directly coordinates `PolicyEngine`, `WorkspaceService`, `FilesystemService`, and `AuditService`.
- **GAP**:
  - The Intelligence Plane does not exist as an independent module; intent parsing is handled directly in MCP dispatchers.
  - The Execution Plane is split across `core/` services and `providers/` without a formal `ExecutionContract` or sandboxed execution coordinator.
- **RECOMMENDATION**:
  - Establish a formal `ExecutionPipeline` that sits between application services and providers.
  - Ensure MCP tools only submit requests to the execution pipeline via typed `ExecutionContract` instances.

---

### Dimension 2: Identity & Principal Context
- **CLAIM**: The system verifies identity and applies zero-trust principal evaluation for all actions.
- **ACTUAL IMPLEMENTATION**: `src/tacp/control/identity.py` defines `Principal(id, role, authenticated)` and `RequestContext(capability, principal, request_id)`. However, `src/tacp/access/mcp/tools.py` hardcodes:
  ```python
  client_principal = principal or Principal(id="mcp-client", role="agent")
  ```
- **EVIDENCE**: `src/tacp/control/identity.py:5-17` and `src/tacp/access/mcp/tools.py:85-88`.
- **GAP**:
  - Principal identity is unauthenticated; caller credentials or tokens are not verified.
  - No differentiation between human operator, autonomous AI agent, background scheduler, or external system.
  - No mechanism to associate session tokens or cryptographic keys with principals.
- **RECOMMENDATION**:
  - Design a comprehensive `IdentityModel` defining 5 principal types (`HUMAN`, `AI_AGENT`, `SYSTEM`, `SCHEDULED_JOB`, `LOCAL_OPERATOR`).
  - Validate principal tokens at the Access Plane boundary before granting context.

---

### Dimension 3: Policy Engine & Hierarchy
- **CLAIM**: Actions are arbitrated by a fine-grained, default-deny policy engine.
- **ACTUAL IMPLEMENTATION**: `src/tacp/control/policy.py` contains `PolicyEngine` with a static set `ALLOWED_CAPABILITIES` (13 read-only capability names). If `context.capability` is in the set, and workspace status is `ACTIVE`, it returns `allowed=True`.
- **EVIDENCE**: `src/tacp/control/policy.py:16-62`.
- **GAP**:
  - The policy engine is binary and static; it has no concept of policy rules, hierarchy (Platform > User > Workspace > Session > Task), autonomy levels (L0-L5), resource conditions, or dynamic constraints.
  - No support for decision types other than `ALLOW` and `DENY` (e.g., `REQUIRE_APPROVAL`, `DEFER`).
- **RECOMMENDATION**:
  - Build a multi-layered `PolicyEngine` supporting hierarchical policy inheritance, decision states (`ALLOW`, `DENY`, `REQUIRE_APPROVAL`, `DEFER`), and fail-closed evaluation.

---

### Dimension 4: Risk Evaluation & Autonomy Levels
- **CLAIM**: Operations are evaluated based on impact risk and autonomous capability boundaries.
- **ACTUAL IMPLEMENTATION**: `src/tacp/control/risk.py` defines `RiskLevel` (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`). `RiskEvaluator.evaluate()` simply maps `"fs.read"` and `"process.inspect"` to `MEDIUM`, everything else to `LOW`, and non-read-only to `CRITICAL`.
- **EVIDENCE**: `src/tacp/control/risk.py:1-19`.
- **GAP**:
  - Risk is not fed into the policy decision in `src/tacp/control/policy.py`.
  - Autonomy levels (L0 through L5) are completely missing.
  - Risk scoring does not account for target resource sensitivity, operation reversibility, or blast radius.
- **RECOMMENDATION**:
  - Implement a 6-tier Risk Engine (`R0` through `R5`) and 6 Autonomy Levels (`L0` through `L5`).
  - Require policy evaluation to compare action risk against principal autonomy ceiling.

---

### Dimension 5: Approval Engine & Human Sovereignty
- **CLAIM**: The system ensures human sovereignty over high-risk actions.
- **ACTUAL IMPLEMENTATION**: Zero approval mechanisms exist in code. There are no tables, services, or APIs for requesting, granting, inspecting, or expiring approvals.
- **EVIDENCE**: Absence of approval references in `src/tacp/`.
- **GAP**:
  - If a mutating capability were added today, it would either execute automatically or fail closed without an interactive approval escalation path.
- **RECOMMENDATION**:
  - Create a dedicated `ApprovalEngine` and database persistence for scoped, time-bound, risk-bounded, and resource-bounded approvals.

---

### Dimension 6: Filesystem Provider & Path Confinement
- **CLAIM**: Filesystem operations are strictly confined to registered workspace roots with multi-layered jailbreak prevention.
- **ACTUAL IMPLEMENTATION**: `src/tacp/providers/filesystem.py` implements `_resolve_in_jail()` using `os.path.realpath()` and string prefix checks, checks for null bytes, enforces 4096-char path limit, and classifies secret files.
- **EVIDENCE**: `tests/security/test_security_baseline_78.py:128-260` (Cases 1–20 all pass).
- **GAP**:
  - Current implementation is 100% read-only (`read_file`, `list_directory`, `stat_file`, `search_files`).
  - No mutation primitives exist (correct for Phase 1, but must be designed for Phase 2).
  - No atomic replace, no file locking, no TOCTOU resistance for mutations.
- **RECOMMENDATION**:
  - Retain `_resolve_in_jail()` as the baseline path guard.
  - Design `workspace.patch` using atomic write-to-temp + fsync + replace + post-verification semantics.

---

### Dimension 7: Command Execution & Process Subsystem
- **CLAIM**: TACP provides an audited command runner and process supervisor.
- **ACTUAL IMPLEMENTATION**: `src/tacp/providers/process.py` provides read-only process enumeration from `/proc` (`list_processes`, `get_process_info`). Zero execution functions exist in runtime.
- **EVIDENCE**: `docs/security/NEGATIVE-API-SURFACE-AUDIT.md` confirms 0 calls to `subprocess.Popen`, `subprocess.run`, `os.system`, or `os.exec*` in production modules.
- **GAP**:
  - Command execution is totally absent.
  - No Job abstraction exists; no tracking of process trees, signals, timeouts, stdout/stderr streams, or resource limits.
- **RECOMMENDATION**:
  - Design a two-tier `JobSystem` and `ProcessManager` separating durable Jobs from ephemeral OS processes.
  - Require strict structured argument arrays (`execve` style) without shell string interpretation.

---

### Dimension 8: Model Context Protocol (MCP) Server
- **CLAIM**: TACP implements the current MCP 2026-07-28 specification with backward compatibility for legacy clients and clean tool exposure.
- **ACTUAL IMPLEMENTATION**:
  - Supports `server/discover`, request-level `_meta`, `cacheScope: "public"`, and legacy `initialize`/`tools/list`/`tools/call`.
  - Exposes exactly 13 read-only tools across 5 domains.
  - Validated by official `@modelcontextprotocol/inspector` v2.6.0 with 0 errors.
- **EVIDENCE**: `src/tacp/access/mcp/protocol.py`, `src/tacp/access/mcp/server.py`, `docs/mcp/inspector-session.md`.
- **GAP**:
  - Tool execution in `src/tacp/access/mcp/tools.py` directly invokes services rather than routing through an execution pipeline.
  - Tools declare empty/basic input schemas rather than strict JSON Schemas with typed output schemas.
  - Tasks extension is not implemented (confirmed absent from official Python SDK v2.2.0).
- **RECOMMENDATION**:
  - Maintain the MCP handler as a thin adapter.
  - Establish a strict MCP Tool Gate requiring input/output schemas, policy mappings, risk ratings, and test contracts before any new Phase 2 tool is exposed.

---

### Dimension 9: Audit Logging & Tamper Evidence
- **CLAIM**: Every operation produces a tamper-evident audit record with cryptographic hash-chaining.
- **ACTUAL IMPLEMENTATION**:
  - `AuditService` writes events to SQLite table `audit_logs` and JSONL file `~/.tacp/audit.log`.
  - Computes SHA-256 hash chaining linking each event to the previous event's hash.
  - `verify_integrity()` recomputes and validates the entire hash chain from genesis.
- **EVIDENCE**: `src/tacp/core/audit_service.py:70-93`, `tests/security/test_security_baseline_78.py:590-630`.
- **GAP**:
  - Does not currently capture execution contracts, approval IDs, diff checksums, or resource usage metrics.
  - Audit verification is an offline/manual check rather than an automatic startup invariant.
- **RECOMMENDATION**:
  - Expand `AuditEvent` schema to record `contract_id`, `approval_id`, `lease_id`, `before_hash`, `after_hash`, and `cpu_user_ms`/`memory_bytes`.
  - Run audit integrity verification during `tacp doctor` and system startup.

---

### Dimension 10: Database Schema & Migrations
- **CLAIM**: State is durably managed in SQLite with WAL mode and migration versioning.
- **ACTUAL IMPLEMENTATION**:
  - `src/tacp/infrastructure/migrations.py` implements versioned migration runner.
  - Migration 1 creates `schema_migrations`, `workspaces`, and `audit_logs`.
- **EVIDENCE**: `src/tacp/infrastructure/migrations.py:4-43`.
- **GAP**:
  - Tables for Principals, Policies, Approvals, Leases, Locks, Jobs, Processes, Artifacts, and Snapshots do not exist.
- **RECOMMENDATION**:
  - Design sequential, reversible SQLite migrations for Phase 2 entities.

---

### Dimension 11: Secret Redaction & Data Classification
- **CLAIM**: Sensitive tokens and private data are protected by multi-layered redaction and data classification.
- **ACTUAL IMPLEMENTATION**:
  - `src/tacp/infrastructure/logging.py` provides regex-based `redact_string()` and `redact_dict()`.
  - Redaction is applied in `fs.read`, `fs.search`, and audit event logging.
- **EVIDENCE**: `tests/security/test_security_baseline_78.py:350-465` (Cases 31–45 all pass).
- **GAP**:
  - Data classification tags (`PUBLIC`, `INTERNAL`, `PRIVATE`, `SENSITIVE`, `SECRET`, `CRITICAL`) exist in `src/tacp/domain/classification.py`, but are not enforced by the policy engine during access decisions.
  - No secret brokering capability exists for safely injecting credentials into child processes without exposing them to the LLM context.
- **RECOMMENDATION**:
  - Enforce data classification as an input to policy decisions.
  - Design an internal `SecretBroker` that injects secrets directly into process environments and scrubs them from outputs.

---

### Dimension 12: Resource Governor & Circuit Breakers
- **CLAIM**: The system guards against denial-of-service, memory bloat, and execution loops.
- **ACTUAL IMPLEMENTATION**:
  - `OutputLimits` in `src/tacp/infrastructure/config.py` bounds read sizes (`max_read_bytes=10MB`, `max_dir_entries=1000`, `max_search_results=100`).
- **EVIDENCE**: `src/tacp/infrastructure/config.py:10-18`.
- **GAP**:
  - No execution time limits, no memory quotas for child tasks, no disk write quotas, and no circuit breakers for repeated failures.
- **RECOMMENDATION**:
  - Design a `ResourceGovernor` managing CPU, memory, disk, execution time, and concurrency quotas per workspace and per job.
  - Design a `CircuitBreaker` that trips to `RECOVERY_REQUIRED` after 4 consecutive failures.

---

### Dimension 13: Test Suite & Verification Gating
- **CLAIM**: The engineering environment enforces 100% reproducible verification with zero tolerance for regressions.
- **ACTUAL IMPLEMENTATION**:
  - 269 automated tests passing across 11 test suites.
  - `./doctor` (15/15 checks) and `./verify` (all 7 stages passing).
- **EVIDENCE**: `artifacts/verification/verification-summary.json`.
- **GAP**:
  - All existing tests validate read-only behavior. Mutation, execution, approval, lease, locking, and recovery test categories do not yet exist.
- **RECOMMENDATION**:
  - Freeze the 269 read-only tests as an immutable regression baseline.
  - Add 200+ new behavioral tests across the 6 Phase 2 domains.

---

### Dimension 14: GitHub Governance & Branch Rules
- **CLAIM**: Repository governance prevents unauthorized direct pushes to `main`.
- **ACTUAL IMPLEMENTATION**: On GitHub Free for personal private repositories, branch protection rulesets are unavailable (HTTP 403). Governance is currently enforced client-side via `./verify`.
- **EVIDENCE**: Documented in `docs/bootstrap/INDEPENDENT-BOOTSTRAP-AUDIT.md`.
- **GAP**: Server-side branch protection cannot be enforced by GitHub without an account plan upgrade.
- **RECOMMENDATION**:
  - Re-verify repository governance in Phase 2. Document as an acknowledged control gap and enforce strict local gating.

---

### Dimension 15: Termux & Android Platform Constraints
- **CLAIM**: TACP operates natively inside Termux without requiring root or modifying system configuration.
- **ACTUAL IMPLEMENTATION**:
  - Fully functional in Termux user namespace (`u0_a316`).
  - Uses native Termux binaries (`clang`, `make`, `ruff`, `python 3.14.6`).
- **EVIDENCE**: Real-device benchmark run recorded in `docs/testing/PERFORMANCE-RESULTS.json`.
- **GAP**:
  - Android battery saver/Doze mode, process suspension, and OOM killer behavior under heavy workloads have not been stress-tested.
- **RECOMMENDATION**:
  - Keep device tests isolated in `tests/device/` and design graceful shutdown/recovery hooks for Android process lifecycle signals.

---

## 3. Summary of Gaps & Architectural Roadblocks

| Area | Status in v0.1.0-rc.1 | Phase 2 Requirement | Gap Severity |
|---|---|---|---|
| **Identity / Principal** | Hardcoded `Principal(id="mcp-client")` | 5 typed principals, cryptographic verification | HIGH |
| **Policy Engine** | Static 13-string allowlist | Hierarchical 5-tier policy engine, 4 decision types | BLOCKER |
| **Risk Engine** | Stub (19 lines, hardcoded) | 6 risk tiers (R0-R5), autonomy levels (L0-L5) | HIGH |
| **Approvals** | None | Scoped, time-bound, risk-bounded approvals | BLOCKER |
| **Execution Contract** | None (direct function calls) | Validated `ExecutionContract` before any operation | BLOCKER |
| **Mutation Engine** | None (read-only) | Atomic `workspace.patch` with checksum & verification | BLOCKER |
| **Command Execution** | None (read-only) | Structured `execution.request` (`execve` semantics) | BLOCKER |
| **Job System** | None | Persistent Job state machine, lifecycle management | HIGH |
| **Concurrency & Locks** | None | Workspace & file locks, leases, stale cleanup | HIGH |
| **Checkpoints & Recovery**| None | Snapshots, state reconciliation, circuit breakers | MEDIUM |
| **Resource Governor** | Static output limits only | CPU, memory, disk, concurrency quotas | HIGH |
| **Network Policy** | None (no network calls) | Domain allowlists, SSRF & private IP guards | MEDIUM |

---

## 4. Conclusion & Gate A Authorization

The repository reconnaissance confirms that the TACP 0.1 read-only baseline is stable, well-tested, and verified, but fundamentally lacks the governance infrastructure required for safe execution. 

Before any mutation or command execution code is introduced, the full architectural design package must be authored, reviewed adversarially, and frozen.
