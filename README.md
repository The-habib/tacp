# TACP — Termux AI Control Plane

> **A secure, auditable, and resilient AI-operated control plane running natively inside Termux on Android.**

[![Verification Pipeline](https://img.shields.io/badge/verification-passing-brightgreen)](#verification--test-metrics)
[![Tests Passing](https://img.shields.io/badge/tests-618%20passing-success)](#verification--test-metrics)
[![Coverage](https://img.shields.io/badge/coverage-83%25-blue)](#verification--test-metrics)
[![MCP Version](https://img.shields.io/badge/MCP-2026--07--28-blueviolet)](#mcp-protocol-conformance)
[![Release](https://img.shields.io/badge/release-v0.4.0--rc.1-orange)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-informational)](LICENSE)

---

## 1. Overview

**TACP (Termux AI Control Plane)** enables AI agents (such as Claude, GPT-4o, and autonomous coding assistants) to safely inspect and mutate development workspaces on Android devices running Termux.

TACP operates on an uncompromising constitutional principle:
> ***"AI MAY BE AUTONOMOUS, BUT AI MUST NEVER BE SOVEREIGN."***

Instead of giving AI agents unrestricted shell access or raw filesystem permissions, TACP acts as an authoritative, policy-governed control layer between the AI agent and the underlying Android operating system. Every action is authenticated, evaluated against strict security policies, guarded by optimistic concurrency locks, and recorded in a tamper-evident cryptographic hash chain.

---

## 2. Core Architecture & Governance Pipeline

TACP enforces a **single, authoritative 16-stage execution pipeline**:

```text
[ AI Agent / MCP Client ]
          │  JSON-RPC 2.0 over Stdio (tools/call)
          ▼
[ McpServer / CLI Engine ]
          │  Extracts correlation IDs, normalizes capability
          ▼
[ McpToolRegistry ]
          │  Constructs RequestContext (Principal, TrustTier, TraceID)
          ▼
[ Domain Service (PatchService / FilesystemService) ]
   ├── 1. Format & Input Validation
   ├── 2. Workspace Resolution & Canonical Path Jail
   ├── 3. Secret Pattern & Path Classification
   ├── 4. PolicyEngine Enforcement (Default-Deny)
   ├── 5. ApprovalEngine (SHA-256 Preimage-Resistant Tickets)
   ├── 6. LockService (Atomic BEGIN IMMEDIATE Serialization)
   ├── 7. Optimistic Concurrency Check (SHA-256 Base Checksum)
   ├── 8. Pre-mutation Snapshot (0700 / 0600 Permissions)
   ├── 9. Same-Directory Atomic Replacement (os.replace)
   └── 10. AuditService (Tamper-Evident SHA-256 Hash Chain)
```

---

## 3. Available Capabilities

### Safe Read-Only Inspection Capabilities (Available to Agents)
| Capability | Description | Input Parameters |
| :--- | :--- | :--- |
| `system.inspect` | Retrieve system hardware, Android kernel, Termux environment | None |
| `system.health` | Diagnostic health check (DB, disk, filesystem) | None |
| `system.version` | Package, schema, and MCP protocol version metadata | None |
| `capabilities.list` | List all registered capabilities and their permission tiers | Optional category filter |
| `workspace.list` | List all registered and active workspaces | None |
| `workspace.inspect` | Inspect detailed workspace configuration and root paths | `workspace_id` |
| `fs.list` | Jailed directory listing within workspace | `workspace_id`, `subpath` |
| `fs.stat` | Jailed file metadata (size, timestamps, checksums) | `workspace_id`, `subpath` |
| `fs.read` | Jailed file reading with automatic secret redaction | `workspace_id`, `subpath` |
| `fs.search` | Content search across workspace files | `workspace_id`, `query` |
| `process.list` | Inspect non-sensitive user processes in Termux | None |
| `process.inspect` | Inspect process details by PID | `pid` |
| `audit.recent` | Inspect recent audit records and verification status | Optional limit |

### Policy-Governed Mutating & Execution Capabilities (Human Approval Required)
| Capability | Description | Governance Rules |
| :--- | :--- | :--- |
| `workspace.patch` | Apply a unified text diff to a single workspace file | Base checksum match + Human Approval Ticket |
| `workspace.patch_batch` | Apply multi-file atomic batch unified diffs | Canonical batch hash + Human Approval Ticket |
| `workspace.rollback` | Revert a single-file patch using stored snapshot | Checksum match; Operator or Approved Agent |
| `workspace.batch_rollback` | Revert an entire batch of patches using manifest | Checksum match; Operator or Approved Agent |
| `execution.request` | Execute governed process (`printf`, `echo`, `true`) | Canonical contract hash + Human Approval Ticket |

---

## 4. Key Security Guarantees

1. **Preimage-Resistant Approval Tokens**: Bearer approval tokens (`tacp_appr_<hex>`) are NEVER persisted to disk. The SQLite database stores only the SHA-256 hash (`token_hash`). Single-use consumption is enforced atomically.
2. **Atomic Concurrency & Lock Serialization**: Lock acquisition uses SQLite `BEGIN IMMEDIATE` transactions to eliminate TOCTOU race conditions. Locks enforce strict owner binding and lease renewals.
3. **Cryptographic Audit Hash Chain**: Every recorded audit event is cryptographically linked to its predecessor using SHA-256 anchored to an immutable genesis (`0`*64). Modifying, deleting, or reordering any record is immediately detected by `verify_integrity()`.
4. **Snapshot Isolation & Mode Preservation**: Snapshots are saved to permission-restricted storage (`0700` dirs, `0600` files). Original file modes are preserved during atomic replacements.
5. **Canonical Path Jailing**: Strict traversal defenses resolve canonical paths against workspace roots, rejecting symlink escapes, null bytes, and path tricks.
6. **Automatic Secret Redaction**: Private keys, GitHub PATs, OpenAI keys, and OAuth tokens are automatically scrubbed from inputs, outputs, errors, and logs.

---

## 5. MCP Protocol Conformance

TACP provides a native, zero-dependency synchronous stdio Model Context Protocol adapter conforming to:
- **MCP 2026-07-28 (Modern Specification)**: Stateless `server/discover`, per-request `_meta` correlation tracking (`requestId`, `progressToken`), and caching semantics (`cacheScope`, `ttlMs`).
- **MCP 2025-11-25 & 2024-11-05 (Legacy Specifications)**: Full bidirectional handshake negotiation (`initialize`, `ping`).
- **Verified via MCP Inspector**: Conformance independently verified against `@modelcontextprotocol/inspector` v2.6.0.

---

## 6. Quick Start & CLI Usage

### Prerequisites
- Android device running [Termux](https://termux.dev) (arm64 recommended).
- Python 3.11+ and `uv` package manager (`pkg install python uv jq ripgrep shellcheck`).

### Installation
```bash
# Clone the repository
git clone https://github.com/thehabib-com/tacp.git
cd tacp

# Run environment diagnostics
./doctor

# Run canonical local verification (all 7 stages)
./verify
```

### CLI Commands
```bash
# Show version and system status
uv run tacp version
uv run tacp status

# List registered workspaces
uv run tacp workspace list

# Register a workspace
uv run tacp workspace register my-project /data/data/com.termux/files/home/projects/my-project

# Launch the stdio MCP server loop for AI clients (with optional execution flag)
uv run tacp serve --allow-execution

# Governed command execution CLI
uv run tacp execution list
uv run tacp execution request --workspace my-project --executable printf --args "Hello World\n" --allow-execution --auto-approve
uv run tacp execution inspect <execution-id>
uv run tacp execution cancel <execution-id>
uv run tacp execution emergency-stop

# Inspect recent audit logs
uv run tacp audit recent
```

---

## 7. Verification & Test Metrics

TACP maintains a deterministic 7-stage verification harness ([`./verify`](verify)):

```bash
$ ./verify
==================================================
           TACP CANONICAL VERIFIER                
==================================================
>>> [Stage 1/7] Hygiene (uv.lock & ShellCheck)... Stage [hygiene]: PASS
>>> [Stage 2/7] Format Check (Ruff)...            Stage [format]: PASS
>>> [Stage 3/7] Lint Check (Ruff)...              Stage [lint]: PASS
>>> [Stage 4/7] Type Check (Mypy)...              Stage [typecheck]: PASS
>>> [Stage 5/7] Unit Tests (pytest)...            Stage [unit_tests]: PASS (329 passed, 83% cov)
>>> [Stage 6/7] Security Test Suite...            Stage [security_tests]: PASS (289 passed)
>>> [Stage 7/7] Dependency Audit (pip-audit)...   Stage [pip_audit]: PASS (0 vulnerabilities)
==================================================
Verification Completed in 65s
Overall Result: PASS
==================================================
```

---

## 8. Measured Performance Benchmarks

Measured on physical Android 13 Termux `aarch64` hardware:

| Metric | Measured Latency / Value | Standard Target |
| :--- | :--- | :--- |
| **Lock Acquire & Release** | **0.11 ms** | < 10.0 ms |
| **Patch Simulation (Dry-Run)** | **1.01 ms** | < 20.0 ms |
| **Patch Live Execution (16 Stages)** | **10.87 ms** | < 50.0 ms |
| **Command Execution (Dry-Run)** | **2.12 ms** | < 20.0 ms |
| **Command Live Execution (16 Stages)** | **17.45 ms** | < 60.0 ms |
| **Patch Rollback Latency** | **2.58 ms** | < 30.0 ms |
| **Audit Hash Chain Full Verification** | **1.13 ms** | < 20.0 ms |
| **Peak Memory Footprint (RSS)** | **28.2 MB** | < 100.0 MB |

---

## 9. Documentation Sitemap

- [Project Constitution](docs/00-PROJECT-CONSTITUTION.md)
- [Product Requirements (PRD)](docs/01-PRD.md)
- [System Architecture](docs/02-ARCHITECTURE.md)
- [Threat Model & Security](docs/04-THREAT-MODEL.md)
- [Controlled Command Execution Architecture](docs/execution/EXECUTION-DESIGN.md)
- [Execution Threat Model](docs/execution/EXECUTION-THREAT-MODEL.md)
- [Execution Security Matrix](docs/execution/EXECUTION-SECURITY-MATRIX.md)
- [Phase 4 Evidence Dossier](docs/evidence/PHASE-4/)
  - [Release Gate Checklist](docs/evidence/PHASE-4/RELEASE-GATE.md)
  - [Current State Audit](docs/evidence/PHASE-4/CURRENT-STATE-AUDIT.md)
  - [Execution Design](docs/evidence/PHASE-4/EXECUTION-DESIGN.md)
  - [Threat Model](docs/evidence/PHASE-4/THREAT-MODEL.md)
  - [Identity Model](docs/evidence/PHASE-4/IDENTITY.md)
  - [Policy Model](docs/evidence/PHASE-4/POLICY.md)
  - [Approval Engine](docs/evidence/PHASE-4/APPROVAL.md)
  - [Process Model](docs/evidence/PHASE-4/PROCESS.md)
  - [Resource Governor](docs/evidence/PHASE-4/RESOURCE-GOVERNOR.md)
  - [Network Containment](docs/evidence/PHASE-4/NETWORK.md)
  - [Security Report](docs/evidence/PHASE-4/SECURITY.md)
  - [Test Suite Report](docs/evidence/PHASE-4/TESTS.md)
  - [MCP Integration](docs/evidence/PHASE-4/MCP.md)
  - [Physical Device Verification](docs/evidence/PHASE-4/DEVICE.md)
  - [Performance Benchmarks](docs/evidence/PHASE-4/PERFORMANCE.md)
  - [Recovery & Orphans](docs/evidence/PHASE-4/RECOVERY.md)
  - [Architecture Review](docs/evidence/PHASE-4/REVIEW.md)
- [Phase 3 Evidence Dossier](docs/evidence/PHASE-3/)

---

## 10. License

MIT License. Copyright (c) 2026 The Habib / TACP Team.
