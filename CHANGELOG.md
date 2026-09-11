# Changelog

All notable changes to the TACP (Termux AI Control Plane) project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.5.0-rc.1] - 2026-09-11

### Phase 6: Local-First Performance, Risk-Adaptive Governance & Trust Profiles

#### Risk-Adaptive Governance & Trust Profiles
- **Risk Ladder ($R_0 \to R_5$)**: Integrated risk categorization (`READ_ONLY`, `MUTATION_REVERSIBLE`, `MUTATION_SIGNIFICANT`, `EXECUTION_CONTROLLED`, `ADMIN_INSPECT`, `SYSTEM_BOUNDARY`) into `RiskEvaluator` and `PolicyEngine`.
- **Trust Profiles**: Introduced `LOCKDOWN`, `STRICT`, `BALANCED` (default), and `DEVELOPER` profiles to allow operators to tailor friction and paranoia levels without modifying code.
- **Dynamic Tool Exposure**: In `LOCKDOWN` mode, mutating and executing tools are stripped from discovery, presenting a read-only surface to clients.
- **Negative Invariant Preserved**: Even in `DEVELOPER` profile, process execution (`execution.request`) strictly requires human approval or an explicit capability lease—the agent is never sovereign.

#### Bounded Capability Leases (Migration 7)
- **Delegated Authority (`CapabilityLease`)**: Time-bounded, budget-limited, and scope-restricted capability leases stored in the new `leases` table with atomic conditional SQLite decrements.
- **Multi-Dimensional Scoping**: Validates principal ID, workspace ID, allowed capability whitelist, resource glob patterns, risk ceilings, and UTC expiration.
- **Instant Revocation**: Supports individual and workspace-wide lease revocation with immediate flight invalidation.

#### Plan-First UX & Grouped Approvals
- **Dry-Run Simulation**: Enables agents to generate simulated diffs and execution plans (`dry_run=True`) for human review.
- **Grouped Approval Tickets**: Added `create_group_ticket` and `verify_and_consume_group` to approve multi-step workflows under a single atomic plan hash.

#### Local-First Performance Optimization
- **In-Memory Caching**: Added thread-safe in-memory caching to `WorkspaceService` with zero staleness risk via `conn.total_changes` detection.
- **Audit Hash Cache**: Tracked latest audit entry hash in-memory in `AuditService` to eliminate preflight SQL queries.
- **Sub-15ms Latency**: Achieved ~1.2ms warm read preflights on Termux `aarch64`.

#### Administrative Capabilities
- **`audit.verify_integrity`**: Exposed cryptographic audit chain verification as an administrative capability for continuous verification.

---

## [0.4.0-rc.1] - 2026-09-11

### Phase 4: Controlled Command Execution (Execution Boundary Architecture & First Vertical Slice)

#### Controlled Process Execution
- **`execution.request`**: Added governed operating system process execution under strict application-level containment with zero unrestricted shell access.
- **First Vertical Slice**: Whitelisted strictly deterministic, non-interpreting utilities (`printf`, `echo`, `true`). Interpreters (`bash`, `sh`, `python`, `node`) and dangerous binaries are strictly forbidden.
- **Immutable ExecutionContract**: Cryptographic SHA-256 canonical hashing across executable, argv, cwd, environment, timeout, and limits.
- **16-Stage Governed Pipeline**: Full deterministic pipeline from request ingestion to audit finalization with dry-run support (`dry_run=True`).
- **Process Group Containment**: `start_new_session=True` (setsid) isolates process groups (PGID == PID) and terminates descendants via `os.killpg(pgid, SIGKILL)` on watchdog timeout or cancellation.
- **Hermetic Environment Assembly**: Base safe environment with curated PATH, temporary directory, and aggressive stripping of sensitive variables and API tokens. Caller environment variables cannot override system-managed variables (`PATH`, `HOME`, `PWD`, `TMPDIR`).
- **Bounded Stream I/O**: Strict 64 KB output buffer limits for stdout and stderr, with automatic ANSI escape sequence scrubbing.
- **SQLite Migration 6**: Created `executions` table tracking complete execution lifecycle, exit codes, termination signals, durations, and output truncation metadata.
- **CLI Commands**: Added `tacp execution request`, `tacp execution list`, `tacp execution inspect`, `tacp execution cancel`, and `tacp execution emergency-stop`.
- **MCP Tool Integration**: Exposed `execution.request` via MCP 2026-07-28 tool registry with structured error envelopes.
- **Verification & Test Suite**: Added 102 execution security test cases (SEC-01 to SEC-102), fuzzing, sabotage, and physical Termux on-device validation. Total test count expanded to 618 passing tests with 83% statement coverage.

---

## [0.3.1-rc.1] - 2026-09-11

### Phase 3: Execution Core Hardening & Pre-Shell / Pre-Android / Pre-Network Security Gate

#### Security & Governance
- **Cryptographic Approval Token Hashing (Migration 4)**: Bearer tokens (`tacp_appr_<hex>`) are never stored in SQLite. Only `sha256(raw_token)` is persisted in the new `token_hash` column.
- **Approver Authority Enforcement**: `ApprovalEngine.approve()` blocks self-approval by agent principals and rejects approvals by untrusted/restricted principals.
- **Atomic Concurrency in Approvals**: Converted ticket consumption to atomic conditional SQL updates, preventing double-spend under high concurrency (10-thread race verified).
- **Serialized Lock Acquisition**: `LockService` upgraded with `BEGIN IMMEDIATE` transactions, atomic expired lock purging, strict ownership checks on release, and lease renewal via `refresh_lock`.
- **Governed Rollback**: Registered `workspace.rollback` and `workspace.batch_rollback` as policy-governed mutating capabilities under `PolicyEngine`.
- **Snapshot Isolation**: Enforced directory mode `0700` and file mode `0600` on snapshot stores; preserved original file permissions across atomic replacements.
- **Tamper-Evident Cryptographic Audit Hash Chain (Migration 5)**: Added `prev_hash` and `entry_hash` to `audit_logs` anchored to an immutable 64-zero genesis. `AuditService.verify_integrity()` proves detection of record modification, deletion, or reordering.
- **Secret Redaction & Error Sanitization**: Sanitized MCP and CLI error strings, redacting sensitive tokens (SSH keys, GitHub PATs, OpenAI keys, OAuth tokens) and shielding internal error traces behind request IDs.

#### Unified Architecture
- **Unified Governance Pipeline**: Eliminated split policy checks and detached audit trails between the MCP layer and domain services. All mutating MCP tools dispatch directly to `PatchService`.
- **Identity & Context Propagation**: Expanded `Principal` model (`PrincipalType`, `TrustTier`, `CredentialSource`) and threaded `RequestContext` (with `request_id` and `trace_id`) from entrypoint to audit log.
- **SQLite Concurrency & Thread Safety**: Converted `Database.connect()` to use `threading.local()` connections with WAL mode and `PRAGMA busy_timeout = 30000`.

#### Diff Parser & Differential Testing
- **Parser Hardening**: Added prefix character validation, hunk count matching, out-of-order/overlapping hunk rejection, CRLF/LF normalization, and multibyte UTF-8 handling.
- **Differential difflib Validation**: Automated tests prove 100% byte-for-byte fidelity with diffs generated by Python's `difflib.unified_diff`.
- **Replay Defense**: Proved that replaying an already-applied patch raises `TacpConflictError`.

#### Infrastructure, CI & Workflows
- **Immutable Action Pinning**: Pinned all GitHub Actions to full 40-character commit SHAs.
- **Dependency Locking**: Enforced `uv sync --locked` and `uv lock --check` in `./verify`.
- **Release Consistency**: Unified version across `src/tacp/__init__.py`, `pyproject.toml`, and runtime services (`0.3.1-rc.1` / `0.3.1rc1`).

#### Design Specifications (Zero Implementation in Phase 3)
- **Controlled Command Execution Design**: Authored `docs/execution/COMMAND-EXECUTION-DESIGN.md` addressing all 17 security design questions (argv model, no `shell=True`, timeouts, process groups, Termux userland constraints).

---

## [0.2.0-rc.1] - 2026-09-11

### Phase 2: Governed Execution Platform (Slices 1 & 2)

#### Added
- **Governed Workspace Patching (`workspace.patch`)**: Single-file text mutation via unified diffs with optimistic concurrency control, same-directory atomic replacement, and automatic snapshot rollback.
- **Batch Workspace Patching (`workspace.patch_batch`)**: Multi-file atomic batch mutation with canonical batch hashing and aggregate rollback manifests.
- **Human Approval Engine**: Scope-bound ticket generation for high-risk operations.
- **Resource Locking**: Cooperative lease-based locks on workspace resources.

---

## [0.1.0-rc.1] - 2026-09-11

### Phase 1 & 1.5: Read-Only Baseline & MCP Modernization

#### Added
- **13 Read-Only Capabilities**: `system.inspect`, `system.health`, `system.version`, `capabilities.list`, `workspace.list`, `workspace.inspect`, `fs.list`, `fs.stat`, `fs.read`, `fs.search`, `process.list`, `process.inspect`, `audit.recent`.
- **Modern MCP Server**: Implemented Model Context Protocol 2026-07-28 specification with backwards compatibility for 2025-11-25 and 2024-11-05.
- **Path Jailing**: Strict workspace boundary enforcement preventing symlink escapes and directory traversal.
- **Verification Harness**: Canonical `./verify` script running formatting, linting, type-checking, unit tests, security test cases, and dependency auditing.
