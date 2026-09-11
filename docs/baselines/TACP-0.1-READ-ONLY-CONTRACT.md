# TACP 0.1 Read-Only Regression Contract

**Document:** `docs/baselines/TACP-0.1-READ-ONLY-CONTRACT.md`  
**Phase:** Baseline Freeze for Phase 2  
**Baseline Release:** `v0.1.0-rc.1` (Commit `a9ad2f1`)  
**Status:** FROZEN & IMMUTABLE REGRESSION BASELINE  
**Date:** September 11, 2026  

---

## 1. Purpose of this Contract

This document freezes the complete behavior, security boundaries, and test suite of **TACP 0.1 (`v0.1.0-rc.1`)** as an immutable regression contract. 

As TACP evolves to introduce governed mutation and execution in Phase 2, **every capability, security invariant, output limit, and MCP guarantee documented here must remain 100% operational and uncompromised**. 

No future change may weaken, bypass, or degrade this baseline.

---

## 2. Frozen Capabilities (13 Read-Only Tools)

The following 13 capabilities are permanently frozen as read-only inspection primitives:

| Capability ID | Tool Name | Scope | Permitted Operations | Mutating Operations |
|---|---|---|---|---|
| `CAP-SYS-001` | `system.version` (`tacp_system_info`) | System | Read host, OS, Termux environment, kernel, uptime | STRICTLY FORBIDDEN |
| `CAP-SYS-002` | `system.health` (`tacp_device_status`) | System | Read battery percentage, charging, temp, network status | STRICTLY FORBIDDEN |
| `CAP-SYS-003` | `system.inspect` (`tacp_termux_environment`) | System | Read Termux prefix, home, shell, package manager details | STRICTLY FORBIDDEN |
| `CAP-SYS-004` | `capabilities.list` (`tacp_list_workspaces`) | Capabilities | Enumerate active registered workspace roots | STRICTLY FORBIDDEN |
| `CAP-WS-001` | `workspace.list` (`tacp_list_workspaces`) | Workspace | List registered workspaces, IDs, and paths | STRICTLY FORBIDDEN |
| `CAP-WS-002` | `workspace.inspect` (`tacp_file_info`) | Workspace | Inspect workspace metadata, root path, trust level | STRICTLY FORBIDDEN |
| `CAP-FS-001` | `fs.list` (`tacp_list_directory`) | Filesystem | Enumerate directory entries with metadata (paginated) | STRICTLY FORBIDDEN |
| `CAP-FS-002` | `fs.stat` (`tacp_file_info`) | Filesystem | Retrieve file size, timestamps, MIME type, permissions | STRICTLY FORBIDDEN |
| `CAP-FS-003` | `fs.read` (`tacp_read_file`) | Filesystem | Read file contents (byte offset/length, secret redacted) | STRICTLY FORBIDDEN |
| `CAP-FS-004` | `fs.search` (`tacp_search_files`) | Filesystem | Glob pattern match files in workspace (redacted) | STRICTLY FORBIDDEN |
| `CAP-PROC-001`| `process.list` (`tacp_list_processes`) | Process | Enumerate running processes in Termux UID namespace | STRICTLY FORBIDDEN |
| `CAP-PROC-002`| `process.inspect` (`tacp_process_info`)| Process | Read PID status, parent PID, cmdline, memory stats | STRICTLY FORBIDDEN |
| `CAP-AUD-001` | `audit.recent` (`tacp_audit_events` / `tacp_verify_integrity`) | Audit | Read audit trail entries, stats, and verify hash chain | STRICTLY FORBIDDEN |

---

## 3. Permanently Unavailable Operations in Read-Only Mode

When TACP operates with `read_only=True` (the default configuration):
1. **Filesystem Writes**: `open(..., 'w')`, `open(..., 'a')`, `open(..., 'x')`, `open(..., '+')` must raise `TacpSecurityError(ErrorCode.READ_ONLY_VIOLATION)`.
2. **Filesystem Deletions**: `os.remove`, `os.unlink`, `os.rmdir`, `shutil.rmtree` must never be called.
3. **Filesystem Modifications**: `os.rename`, `shutil.move`, `os.chmod`, `os.chown` must never be called.
4. **Shell / Command Execution**: `subprocess.run`, `subprocess.Popen`, `os.system`, `os.exec*` must never be called by read-only tools.
5. **Privilege Escalation**: `su`, `sudo`, `setuid`, or root binary invocations are completely prohibited.
6. **Outbound Sockets**: No direct outbound network connections may be initiated during runtime tool execution.

---

## 4. Frozen Security Invariants

The following 12 security invariants are enforced by automated test harnesses and must never regress:

- **INVARIANT 1 (Policy Protection)**: AI agents cannot modify, overwrite, delete, or escalate security policies.
- **INVARIANT 2 (Workspace Confinement)**: AI agents cannot escape authorized workspace roots. Path traversal (`..`, `../..`), symlink dereferencing escaping roots, absolute path escapes, and null byte injections must fail closed.
- **INVARIANT 3 (Secret Protection)**: AI agents cannot view protected secrets (`.env`, `.key`, `.pem`, `id_rsa`, `id_ed25519`, `credentials.json`, `.bash_history`). Secret content is scrubbed by multi-pattern regex redaction in file reads, search snippets, and audit logs.
- **INVARIANT 4 (Default-Deny)**: Unknown or ambiguous capabilities, unauthenticated principals, or unrecognized parameters must evaluate to `DENY` or `REQUIRE_APPROVAL`. Ambiguity never converts to `ALLOW`.
- **INVARIANT 5 (Approval Expiry)**: Expired approvals or forged approval tokens do not authorize actions.
- **INVARIANT 6 (Lease Expiry)**: Expired capability or resource leases do not authorize actions.
- **INVARIANT 7 (Read-Only Immunity)**: In read-only mode, no action may mutate the filesystem, process tree, or configuration.
- **INVARIANT 8 (Audit Integrity)**: Every tool invocation, success, and rejection writes an audit event with SHA-256 hash chaining. Tampering, reordering, deletion, or modification of historical records is cryptographically detected.
- **INVARIANT 9 (Resource Limits)**: Resource limits (read sizes, line limits, process limits) cannot be silently bypassed. Boundary violations fail closed.
- **INVARIANT 10 (Instruction/Data Separation)**: Content read from repository files, web pages, or logs is strictly data. It cannot redefine platform authority, policy, or permissions.
- **INVARIANT 11 (Verifier Integrity)**: A failed security check cannot be converted into `PASS` by modifying the test runner or bypassing `./verify`.
- **INVARIANT 12 (Emergency Local Stop)**: Emergency stop controls must be locally accessible and cannot be disabled or blocked by remote agents.

---

## 5. Frozen Output & Resource Limits

| Resource Limit | Value | Enforcement Behavior |
|---|---|---|
| `max_read_bytes` | 10,485,760 bytes (10 MB) | Truncates with warning or raises `TacpValidationError` |
| `max_dir_entries` | 1,000 entries | Truncates directory listing to first 1,000 entries |
| `max_search_results` | 100 entries | Truncates search results to first 100 matches |
| `max_path_length` | 4,096 characters | Rejects path with `TacpSecurityError(OUTSIDE_WORKSPACE)` |
| `max_stat_cache` | 1,000 entries | Invalidation on workspace state change |

---

## 6. Frozen MCP Protocol Guarantees

1. **Protocol Specifications**: Supports both `2026-07-28` (modern) and `2024-11-05` through `2025-11-25` (legacy).
2. **Stateless Discovery**: `server/discover` returns supported versions, capabilities, `cacheScope: "public"`, `ttlMs: 60000`, and `resultType: "complete"`.
3. **Legacy Handshake**: `initialize` negotiates protocol version; `notifications/initialized` completes handshake; `ping` returns `{}`.
4. **Tool Metadata**: Every tool exposed via `tools/list` provides a valid JSON Schema object (`{"type": "object", "properties": {...}}`).
5. **No Direct MCP-to-OS Path**: MCP handlers are thin protocol adapters. They must NEVER call OS primitives directly (`subprocess`, `open`, `os.system`). All actions route through the application service and policy engine.
6. **Error Format**: Returns standard JSON-RPC 2.0 error objects (`code`, `message`, `data`) with suppressed internal stack traces.

---

## 7. Regression Test Suite Guarantee

The existing **269 automated tests** covering:
- Unit tests (80 tests)
- MCP contract tests (31 tests)
- Integration tests (46 tests)
- Security baseline tests (78 tests)
- Negative API surface tests (12 tests)
- Recovery and persistence tests (10 tests)
- OpenAI tunnel emulation tests (4 tests)
- Installer integration tests (6 tests)
- Pipeline gates (`./doctor` 15/15, `./verify` 7/7)

**MUST BE EXECUTED ON EVERY PHASE 2 BUILD**. Any regression in these 269 tests is an immediate **BLOCKER** that halts progression.
