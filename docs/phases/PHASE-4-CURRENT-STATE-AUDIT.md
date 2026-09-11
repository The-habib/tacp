# TACP Phase 4 — Current State Audit & Execution Boundary Assessment
## Pre-Shell / Pre-Android / Pre-Network Security Gate

- **Date:** September 11, 2026
- **Current Reported Release:** `v0.3.1-rc.1` (`0.3.1rc1`)
- **Current Commit:** `5eda9dd`
- **Platform:** Android 13 / Termux (Linux 5.15.197 aarch64, Python 3.14.6)
- **Status:** **GATE A COMPONENT AUDIT — EMPIRICAL REPOSITORY BASELINE**

---

## 1. Executive Summary & Constitutional Premise

This audit establishes the empirical technical baseline for **Phase 4: Controlled Command Execution (Execution Boundary Architecture + First Execution Vertical Slice)**.

**Constitutional Axiom:**
> **"Operating-system process execution introduces a new security boundary. TACP must never expose an unrestricted shell (`bash -c`, `sh`, `os.system`, `shell=True`). Power must never outpace control."**

In Phases 1 through 3, TACP established a hardened read-only inspection baseline and governed filesystem mutation primitives (`workspace.patch`, `workspace.patch_batch`). Command execution operates at a fundamentally higher level of power. A child process inherits operating-system capabilities, consumes CPU, memory, file descriptors, and network sockets, and can spawn descendants.

Therefore, this audit independently reviews all 20 core subsystems in the current repository to determine what can be reused, what must be hardened before execution code is written, and what new components are required.

---

## 2. Component-by-Component Empirical Audit

### 1. Process Provider (`src/tacp/providers/process.py`)
- **CURRENT IMPLEMENTATION:** Pure read-only inspection of `/proc`. Implements `list_processes()` and `inspect_process(pid)`. Filters processes by current Termux UID (`os.getuid()`), reads `cmdline`, `comm`, `status`, `stat`, and sanitizes null bytes. Enforces `OutputLimits.max_processes`.
- **SECURITY ROLE:** Passive process table visibility and read-only telemetry. Prevents inspection of cross-UID Android OS or other app processes.
- **REUSABILITY:** High for read-only inspection; completely non-reusable for process spawning or execution lifecycle management.
- **WEAKNESS:** Cannot spawn, monitor, signal, or manage child process trees. Contains no process group creation, signal propagation, or PID reuse detection logic.
- **CHANGE REQUIRED:** Keep `ProcessProvider` strictly as a read-only telemetry provider. Create a separate dedicated, isolated `ProcessExecutor` provider (`src/tacp/providers/process_executor.py`) responsible for launching processes under `start_new_session=True` (`os.setsid`), controlling file descriptors, reading bounded output streams, and managing process termination signals (`SIGTERM` -> grace period -> `SIGKILL`).

---

### 2. Process Service (`src/tacp/core/process_service.py`)
- **CURRENT IMPLEMENTATION:** Minimal facade forwarding `list_processes()` and `inspect_process(pid)` to `ProcessProvider`.
- **SECURITY ROLE:** Business logic layer for read-only process operations.
- **REUSABILITY:** Reusable for process telemetry queries (`process.list`, `process.inspect`).
- **WEAKNESS:** Lacks any execution lifecycle awareness, job tracking, process ownership mapping, or execution record persistence.
- **CHANGE REQUIRED:** Keep `ProcessService` focused on read-only system process queries. Implement a dedicated `ExecutionService` (`src/tacp/core/execution_service.py`) that coordinates execution contracts, policy evaluation, approval verification, process launching, stdout/stderr bounding, exit code capture, audit logging, and process-tree termination.

---

### 3. MCP Server (`src/tacp/access/mcp/server.py`)
- **CURRENT IMPLEMENTATION:** Synchronous stdio JSON-RPC 2.0 server supporting both MCP `2026-07-28` (`server/discover`, stateless discovery) and `2024-11-05` (`initialize`) protocol versions. Dispatches `tools/list` and `tools/call` via `McpToolRegistry`. Formats output content blocks and handles structured error envelopes (`McpResponse.fail`).
- **SECURITY ROLE:** Protocol boundary between external AI agents / IDEs and the TACP control plane.
- **REUSABILITY:** High. Protocol parsing, message dispatch, error serialization, and secret redaction are production-ready.
- **WEAKNESS:** Does not currently support or expose `execution.*` tools. Assumes all incoming calls over stdio are `Principal.local_agent("mcp-client")`. Lacks distinction between local stdio callers and tunnelled remote callers.
- **CHANGE REQUIRED:** Add support for `execution.request` tool. Ensure tool is conditionally omitted or denied when `execution_enabled = False`. Preserve existing protocol conformance.

---

### 4. MCP Tool Registry (`src/tacp/access/mcp/tools.py`)
- **CURRENT IMPLEMENTATION:** Central dispatcher for MCP `tools/list` and `tools/call`. Resolves tools by name (supporting `tacp_` prefix and dot/underscore variants). Enforces read-only capabilities through `PolicyEngine` and delegates mutating calls directly to `PatchService`.
- **SECURITY ROLE:** Translates MCP tool calls into governed domain requests with caller context and request correlation IDs.
- **REUSABILITY:** High architecture alignment.
- **WEAKNESS:** Lacks dispatch routing for `execution.request`.
- **CHANGE REQUIRED:** Add `execution.request` to `McpToolRegistry`. When `config.execution_enabled = False`, omit `execution.request` from `tools/list` and reject `tools/call` with `TacpSecurityError(ErrorCode.POLICY_DENIED)`. Forwards execution parameters directly to `ExecutionService`.

---

### 5. Policy Engine (`src/tacp/control/policy.py`)
- **CURRENT IMPLEMENTATION:** Evaluates incoming request capabilities against `ALLOWED_CAPABILITIES` (read-only) and `MUTATING_CAPABILITIES` (`workspace.patch`, `workspace.patch_batch`, `workspace.rollback`, `workspace.batch_rollback`). Validates path traversal (`..`), protected patterns (`.git`, `.tacp`, `tacp.db`, `.env`, SSH keys), and approval presence. Supports `dry_run=True`.
- **SECURITY ROLE:** Central authoritative gatekeeper enforcing default-deny access control across all operations.
- **REUSABILITY:** High for structural policy evaluation; requires extension for command execution governance.
- **WEAKNESS:** Contains legacy string checks for principal role/id (`context.principal.role == "operator" or context.principal.id in ("operator", "human_operator")`). Does not yet evaluate command classifications (SAFE, CONTROLLED, DANGEROUS, CRITICAL), executable whitelists, argument injection, or network policy.
- **CHANGE REQUIRED:**
  1. Add `EXECUTION_CAPABILITIES = {"execution.request", "execution.inspect", "execution.list", "execution.cancel"}`.
  2. Guard execution under `self.execution_enabled` (default `False`).
  3. Validate executable path, arguments, environment variables, working directory, and network access flags.
  4. Replace legacy string matches with typed checks (`principal.principal_type == PrincipalType.HUMAN and principal.trust_tier == TrustTier.PRIVILEGED`).
  5. Enforce approval requirement for non-dry-run execution requests.

---

### 6. Identity Model (`src/tacp/control/identity.py`)
- **CURRENT IMPLEMENTATION:** Defines `PrincipalType` (`AGENT`, `HUMAN`, `SYSTEM`), `TrustTier` (`UNTRUSTED`, `RESTRICTED`, `PRIVILEGED`), `CredentialSource` (`LOCAL_STDIO`, `TOKEN`, `SYSTEM`, `NONE`), immutable `Principal` dataclass, and `RequestContext` with UUID request/trace IDs.
- **SECURITY ROLE:** Defines caller identity, trust levels, and audit tracking context.
- **REUSABILITY:** Fully reusable typed data structures.
- **WEAKNESS:** Callers over stdio default to `Principal.local_agent("mcp-client")` without cryptographic token authentication. Downstream consumers historically checked string names rather than typed properties.
- **CHANGE REQUIRED:** Remove all residual string-based identity checks in callers. Ensure execution commands cannot be authorized or approved by `PrincipalType.AGENT` regardless of principal ID naming.

---

### 7. Approval Engine (`src/tacp/control/approval.py`)
- **CURRENT IMPLEMENTATION:** Generates `ApprovalTicket` with SHA-256 hashed bearer tokens stored in SQLite `approvals` table. Implements 5-dimensional scope checking (`action_type`, `workspace_id`, `target_path`, `patch_hash`, `principal_id`). Enforces single-use consumption with atomic SQL update.
- **SECURITY ROLE:** Human-in-the-loop authorization barrier for high-risk operations.
- **REUSABILITY:** High core architecture.
- **WEAKNESS:**
  1. Concurrency flaw in `approve()`, `deny()`, and `revoke()`: updates SQLite status without conditionally verifying the prior status in the `WHERE` clause (`WHERE token_hash = ? AND status = 'PENDING'`). A concurrent revoke or expire could be overwritten by a delayed approve.
  2. Scope model is tailored to `target_path` and `patch_hash` rather than `ExecutionContract` (`executable`, `argv`, `cwd`, `environment`, `network_enabled`, `timeout_seconds`).
- **CHANGE REQUIRED:**
  1. Add conditional SQL updates (`WHERE token_hash = ? AND status = 'PENDING'`) to `approve()`, `deny()`, and `revoke()`, asserting `rowcount == 1`.
  2. Support execution approval tickets where `action_type = 'execution.request'`, `target_path = executable`, and `patch_hash = canonical_contract_hash`.
  3. Enforce single-use consumption strictly on execution dispatch.

---

### 8. Lock Service (`src/tacp/core/lock_service.py`)
- **CURRENT IMPLEMENTATION:** SQLite-backed mutual exclusion lock (`locks` table) with expiration timeouts, ownership tokens, and `BEGIN IMMEDIATE` transaction serialization.
- **SECURITY ROLE:** Prevents concurrent race conditions and conflicting mutations on identical resources.
- **REUSABILITY:** Fully reusable.
- **WEAKNESS:** Scoped to filesystem paths (e.g. `workspace:{id}:{path}`). Does not have a lock scope for execution concurrency if exclusive resource locks are needed.
- **CHANGE REQUIRED:** Allow execution locks on `execution:{workspace_id}` or `execution:{execution_id}` to serialize execution requests if single-concurrency workspace execution policy is configured.

---

### 9. Audit Service (`src/tacp/core/audit_service.py`)
- **CURRENT IMPLEMENTATION:** Tamper-evident linear cryptographic hash chain (`prev_hash` -> `entry_hash` via canonical JSON SHA-256). Redacts parameters before serialization. Implements `verify_integrity()`.
- **SECURITY ROLE:** Immutable provenance and non-repudiation log for all governance actions.
- **REUSABILITY:** High cryptographic core.
- **WEAKNESS:** Concurrent append race! In `record_event()`, `SELECT entry_hash FROM audit_logs ORDER BY rowid DESC LIMIT 1` occurs inside `with conn:` (deferred transaction). Concurrent writers can read the identical `prev_hash` before either inserts, creating forked chain entries that break `verify_integrity()`.
- **CHANGE REQUIRED:**
  1. Enforce strict transaction serialization using `conn.execute("BEGIN IMMEDIATE;")` prior to reading `latest entry_hash`.
  2. Add an in-process thread `threading.Lock()` to serialize multi-threaded appends.
  3. Write exhaustive concurrency test proving that simultaneous multi-threaded writers produce a strictly linear, valid cryptographic hash chain.

---

### 10. Database & Migrations (`src/tacp/infrastructure/database.py`, `migrations.py`)
- **CURRENT IMPLEMENTATION:** SQLite3 with WAL mode, foreign keys enabled, busy timeout (5000ms), and versioned schema migrations (Versions 1–5).
- **SECURITY ROLE:** Durable state storage for workspaces, policies, principals, approvals, patches, batches, locks, and audit logs.
- **REUSABILITY:** High reliability.
- **WEAKNESS:** No schema table exists for tracking execution instances, execution metadata, process group IDs, exit codes, output status, or termination reasons.
- **CHANGE REQUIRED:** Add Migration 6 creating `executions` table with columns: `id`, `execution_id`, `action_type`, `workspace_id`, `executable`, `argv_json`, `cwd`, `contract_hash`, `principal_id`, `status`, `exit_code`, `term_signal`, `duration_ms`, `stdout_truncated`, `stderr_truncated`, `timed_out`, `cancelled`, `pid`, `pgid`, `created_at`, `started_at`, `terminated_at`, `metadata_json`.

---

### 11. Configuration (`src/tacp/infrastructure/config.py`)
- **CURRENT IMPLEMENTATION:** Frozen `TacpConfig` and `OutputLimits`. Reads environment variables with secure defaults (`read_only = True`, `mutation_enabled = False`, `batch_mutation_enabled = False`).
- **SECURITY ROLE:** Authoritative configuration source preventing unintended capability exposure.
- **REUSABILITY:** High pattern alignment.
- **WEAKNESS:** Lacks execution configuration flags (`execution_enabled`, `network_enabled`, `remote_execution_enabled`) and execution limits (duration, stdout/stderr byte limits, argv count/length limits).
- **CHANGE REQUIRED:** Add to `TacpConfig`:
  - `execution_enabled: bool = False` (env: `TACP_EXECUTION_ENABLED`, default `False`)
  - `network_enabled: bool = False` (env: `TACP_NETWORK_ENABLED`, default `False`)
  - `remote_execution_enabled: bool = False` (env: `TACP_REMOTE_EXECUTION_ENABLED`, default `False`)
  Add to `OutputLimits`:
  - `max_execution_duration_seconds: int = 15`
  - `max_stdout_bytes: int = 65536`
  - `max_stderr_bytes: int = 65536`
  - `max_argv_count: int = 64`
  - `max_arg_length: int = 4096`

---

### 12. Workspace Service (`src/tacp/core/workspace_service.py`)
- **CURRENT IMPLEMENTATION:** Validates workspace root paths against `allowed_workspace_roots`, resolves canonical paths via `realpath()`, checks directory existence, and manages active workspace status in the database.
- **SECURITY ROLE:** Enforces filesystem containment boundary preventing path escapes.
- **REUSABILITY:** Fully reusable.
- **WEAKNESS:** Does not validate whether a requested execution working directory (`cwd`) lies strictly within the active workspace root.
- **CHANGE REQUIRED:** Use `WorkspaceService.validate_path` or canonical path containment checks to ensure execution `cwd` is strictly imprisoned within the resolved workspace root.

---

### 13. Patch Service (`src/tacp/core/patch_service.py`)
- **CURRENT IMPLEMENTATION:** 16-stage pipeline for single-file and multi-file patches: policy validation, ticket issuance, token consumption, resource locking, base checksum verification, snapshot creation, unified diff application, atomic replacement, rollback registration, and audit logging.
- **SECURITY ROLE:** Demonstrates the canonical pattern for governed mutating operations in TACP.
- **REUSABILITY:** High architectural template.
- **WEAKNESS:** Specialized exclusively for text filesystem mutation; not applicable to process execution.
- **CHANGE REQUIRED:** None to `PatchService` itself. Use its 16-stage pipeline pattern as the direct architectural model for `ExecutionService`.

---

### 14. Command-Line Interface (`src/tacp/cli/main.py`)
- **CURRENT IMPLEMENTATION:** Click-based CLI offering commands for system inspection, workspace management, filesystem operations, process inspection, audit review, patch execution, and approval management.
- **SECURITY ROLE:** Human operator interface and primary administrative entry point.
- **REUSABILITY:** Clean command tree.
- **WEAKNESS:** Lacks CLI subcommands for execution operations (`tacp execution request`, `tacp execution inspect`, `tacp execution list`, `tacp execution cancel`, emergency stop).
- **CHANGE REQUIRED:** Add `tacp execution` command group with subcommands:
  - `request`: submits execution request with `--dry-run` or `--approval-token`
  - `inspect`: inspects execution state and output metadata
  - `list`: lists execution history
  - `cancel`: cancels active execution
  - `emergency-stop`: terminates all TACP-owned execution processes

---

### 15. Test Suite (`tests/`)
- **CURRENT IMPLEMENTATION:** 470 automated tests covering unit, integration, security, failure injection, and device verification.
- **SECURITY ROLE:** Automated regression prevention and security guarantee verification.
- **REUSABILITY:** High baseline.
- **WEAKNESS:** 0 tests currently test process execution, execution pipeline, process-group killing, stdout/stderr byte truncation, signal dispatch, or execution security vectors.
- **CHANGE REQUIRED:** Create comprehensive test suites:
  - `tests/unit/test_audit_concurrency.py`: multi-threaded concurrent audit append stress test.
  - `tests/unit/test_approval_state_machine.py`: multi-threaded concurrent approval transition test.
  - `tests/unit/test_execution_contract.py`: canonical contract hashing and immutability tests.
  - `tests/unit/test_execution_resolver.py`: binary resolution, path containment, and environment stripping tests.
  - `tests/unit/test_execution_service.py`: execution lifecycle, dry-run, output bounding, and timeout tests.
  - `tests/security/test_execution_security.py`: 100+ execution security tests covering all Part 51 attack vectors.
  - `tests/unit/test_execution_fuzzing.py` & `test_execution_sabotage.py`: fuzzing and failure injection tests.

---

### 16. Continuous Integration (`.github/workflows/ci.yml`)
- **CURRENT IMPLEMENTATION:** GitHub Actions workflow running on Ubuntu 24.04 with pinned commit SHAs, Python 3.12, `uv sync --locked`, Ruff format, Ruff check, Mypy, and Pytest (unit, integration, and non-device tests).
- **SECURITY ROLE:** Supply-chain integrity and regression gate on push/PR.
- **REUSABILITY:** Fully functional.
- **WEAKNESS:** Does not run execution tests yet.
- **CHANGE REQUIRED:** Ensure new unit, integration, and security execution tests run cleanly in CI without requiring Android-specific `/system/bin` paths (using POSIX fallback binaries like `/usr/bin/printf` or mocked resolution where appropriate).

---

### 17. Security Workflow (`.github/workflows/security.yml`)
- **CURRENT IMPLEMENTATION:** Pinned actions workflow running Bandit AST scan and `pip-audit` vulnerability checks.
- **SECURITY ROLE:** Automated static vulnerability and dependency CVE auditing.
- **REUSABILITY:** Fully functional.
- **WEAKNESS:** Bandit may flag subprocess invocation if not properly structured or if using shell-like constructs.
- **CHANGE REQUIRED:** Ensure all subprocess invocations use explicit `argv: List[str]` and `shell=False`. Ensure Bandit rules pass with 0 warnings or explicit justifiable `# nosec` annotations on safe `subprocess.Popen` calls.

---

### 18. Device Tests (`tests/device/`)
- **CURRENT IMPLEMENTATION:** Physical Termux validation suite verifying Android 13/Linux kernel characteristics: `/proc` filesystem permissions, UID isolation, symlink resolution, SQLite WAL performance, and signal behavior.
- **SECURITY ROLE:** Verifies runtime assumptions on the actual target mobile deployment platform.
- **REUSABILITY:** High value.
- **WEAKNESS:** Does not yet test Termux-specific process execution behavior, process groups, Termux binary paths (`/data/data/com.termux/files/usr/bin/printf`), or memory/CPU reality.
- **CHANGE REQUIRED:** Add `tests/device/test_termux_execution.py` verifying real Termux binary resolution, process-group creation (`os.setsid`), child cleanup, and execution performance.

---

### 19. Project Documentation (`docs/`)
- **CURRENT IMPLEMENTATION:** Comprehensive architecture specs, threat models, runbooks, baselines, ADRs, and evidence directories for Phases 1 through 3.
- **SECURITY ROLE:** Authoritative specification and audit trail.
- **REUSABILITY:** Excellent structure.
- **WEAKNESS:** Contains preliminary Phase 3 command execution design notes (`docs/execution/COMMAND-EXECUTION-DESIGN.md`), but lacks the required Gate A execution architecture, threat model, process model, environment model, resource model, security matrix, state machine, and design review.
- **CHANGE REQUIRED:** Author all Gate A deliverables:
  - `docs/execution/EXECUTION-DESIGN.md`
  - `docs/execution/EXECUTION-THREAT-MODEL.md`
  - `docs/execution/EXECUTION-CONTRACT.md`
  - `docs/execution/PROCESS-MODEL.md`
  - `docs/execution/ENVIRONMENT-MODEL.md`
  - `docs/execution/RESOURCE-MODEL.md`
  - `docs/execution/NETWORK-MODEL.md`
  - `docs/execution/EXECUTION-SECURITY-MATRIX.md`
  - `docs/execution/EXECUTION-STATE-MACHINE.md`
  - `docs/mcp/EXECUTION-MCP-CONTRACT.md`
  - `docs/phases/PHASE-4-DESIGN-REVIEW.md`

---

### 20. Antigravity Governance & Constitution (`docs/00-PROJECT-CONSTITUTION.md`, rules)
- **CURRENT IMPLEMENTATION:** 12 constitutional articles establishing human supremacy, least privilege, fail-closed defaults, audit irrevocability, and empirical verification standards.
- **SECURITY ROLE:** Ultimate normative framework governing all development decisions.
- **REUSABILITY:** Irrevocable foundation.
- **WEAKNESS:** None. The constitution already anticipates Phase 4: Article 1 forbids unconstrained autonomy; Article 2 forbids shell execution; Article 3 requires verifiable isolation.
- **CHANGE REQUIRED:** Strictly enforce constitutional rules during Phase 4 implementation. Reject any proposal for interactive shells, arbitrary command strings, or autonomous execution loops.

---

## 3. Summary of Audit Conclusions & Gate B Pre-Conditions

Before writing any execution engine code, the following three hardening fixes must be implemented:
1. **Audit Append Serialization:** Introduce `BEGIN IMMEDIATE` + thread-level locking to prevent hash chain branching under concurrent writes.
2. **Approval State Machine Hardening:** Enforce conditional SQL status transitions (`WHERE token_hash = ? AND status = 'PENDING'`) across `approve()`, `deny()`, and `revoke()`.
3. **Identity Demarcation:** Remove legacy string identity checks in favor of typed `PrincipalType` and `TrustTier` attributes.

**Audit Status:** APPROVED — BASELINE EMPIRICALLY CONFIRMED.
