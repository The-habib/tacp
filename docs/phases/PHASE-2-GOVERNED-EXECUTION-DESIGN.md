# TACP Phase 2 — Governed Execution Platform Master Design

**Document:** `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**Status:** DRAFT PROPOSAL FOR ADVERSARIAL REVIEW  
**Principal Architect:** Antigravity Engineering Factory  
**Date:** September 11, 2026  

---

## 1. Vision & Core Constitutional Principle

Phase 2 transitions TACP from a verified read-only inspection engine into a **Governed Execution Platform**.

The mission of Phase 2 is not simply to provide mutation or command execution capabilities (such as `fs.write` or `shell.exec`). Instead, it is to build the **universal governance fabric** within which any powerful capability can be safely operated by AI agents on Android Termux.

### The Sovereign Constitutional Rule
> **"AI MAY BE AUTONOMOUS, BUT AI MUST NEVER BE SOVEREIGN."**
>
> An AI agent may propose actions, generate code patches, recommend commands, and execute approved plans within bounded constraints. However, supreme authority, policy definition, privilege escalation, and high-impact approvals remain permanently reserved to the **Human Operator / Project Owner**.

---

## 2. Five-Plane Architecture Model

TACP maintains a strict five-plane architecture with downward-only dependency flow. Higher planes consume abstractions of lower planes; lower planes have zero knowledge of higher planes.

```
+========================================================================+
| 1. ACCESS PLANE (mcp, sse, stdio, cli, tunnel)                         |
|    - Protocol framing, transport handling, initial message validation  |
+========================================================================+
                                   |
                                   v
+========================================================================+
| 2. INTELLIGENCE PLANE (intent, plan, task, schema adapter)             |
|    - Translates external requests into structured Intents & Tasks      |
+========================================================================+
                                   |
                                   v
+========================================================================+
| 3. CONTROL PLANE (identity, policy, risk, approval, lease, audit)      |
|    - Evaluates authority, assigns risk, verifies approvals/leases     |
|    - Issues validated, immutable ExecutionContract                     |
+========================================================================+
                                   |
                                   v
+========================================================================+
| 4. EXECUTION PLANE (contract runner, patch, job, lock, checkpoint)     |
|    - Dispatches validated ExecutionContract; enforces limits & locks   |
+========================================================================+
                                   |
                                   v
+========================================================================+
| 5. PLATFORM / PROVIDER PLANE (filesystem, process, termux, android)    |
|    - Atomic OS operations, /proc readers, child process supervision    |
+========================================================================+
```

### Invariant: Absolute Separation of MCP from OS Primitives
Direct calls from MCP handlers to operating system mutation or execution primitives are **strictly forbidden**.

```
[FORBIDDEN] MCP Handler ----> subprocess.run() / open('w') / os.system()
[REQUIRED]  MCP Handler ----> Application Service ----> Control Pipeline ----> Provider ----> OS
```

---

## 3. The 16-Stage Governed Execution Pipeline

Every mutating, executing, or sensitive operation must traverse the 16-stage pipeline without bypass:

```
[1. REQUEST]
     │
[2. IDENTITY RESOLUTION]       --> Resolves & authenticates Principal (Human, Agent, System)
     │
[3. CAPABILITY RESOLUTION]     --> Resolves capability against CapabilityRegistry
     │
[4. RESOURCE RESOLUTION]       --> Resolves canonical target (workspace/file/job/network)
     │
[5. INPUT VALIDATION]          --> Validates against strict JSON Schema & type invariants
     │
[6. POLICY EVALUATION]         --> Evaluates 5-tier policy hierarchy (Platform > User > WS...)
     │
[7. RISK CLASSIFICATION]       --> Calculates Risk Level (R0 to R5) & Autonomy Level (L0-L5)
     │
[8. BUDGET & RESOURCE CHECK]   --> Verifies CPU, memory, disk, and execution time quotas
     │
[9. LOCK & LEASE CHECK]        --> Acquires concurrency lock and checks active lease
     │
[10. APPROVAL CHECK]           --> Verifies scoped, unexpired human approval if required
     │
[11. EXECUTION CONTRACT]       --> Binds all validated parameters into an immutable Contract
     │
[12. EXECUTOR DISPATCH]        --> Invokes sandboxed Provider operation (e.g. atomic patch)
     │
[13. OBSERVATION CAPTURE]      --> Captures structured raw result, metrics, and exit codes
     │
[14. OUTPUT SANITIZATION]      --> Scrubs secrets, terminal escapes, and truncates limits
     │
[15. AUDIT EVENT LOGGING]      --> Cryptographically records chained SHA-256 audit entry
     │
[16. RESULT DISPATCH]          --> Formats and returns safe response to caller
```

---

## 4. Domain Model Overview

The Phase 2 platform is structured around formal, typed domain entities:

| Entity | Primary Purpose | Lifecycle States | Storage |
|---|---|---|---|
| **Principal** | Represents the actor initiating an action | `ACTIVE`, `SUSPENDED`, `REVOKED` | Database |
| **Workspace** | Bounded filesystem sandbox for operations | `ACTIVE`, `LOCKED`, `READ_ONLY`, `ARCHIVED` | Database |
| **Capability**| Declares a platform operation & its contract | `DESIGNED` → `STABLE` → `DEPRECATED` | Code & DB |
| **Policy** | Rules determining authorization | `ACTIVE`, `INACTIVE`, `OVERRIDDEN` | Database |
| **Approval** | Time- & resource-bound human authorization | `REQUESTED`, `GRANTED`, `DENIED`, `EXPIRED`, `CONSUMED` | Database |
| **Lease** | Temporary capability/resource authorization | `ACTIVE`, `EXPIRED`, `REVOKED` | Memory/DB |
| **Lock** | Concurrency control over workspaces/files | `ACQUIRED`, `RELEASED`, `EXPIRED` | Memory/DB |
| **ExecutionContract** | Immutable binding authorizing an execution | `CREATED`, `EXECUTING`, `COMPLETED`, `FAILED` | Memory/DB |
| **Job** | Durable, trackable unit of execution | `CREATED`, `RUNNING`, `PAUSED`, `SUCCEEDED`, `FAILED`, `CANCELLED` | Database |
| **Process** | Operating system process owned by a Job | `SPAWNED`, `RUNNING`, `EXITED`, `TERMINATED` | Ephemeral |
| **Snapshot** | Checkpoint of workspace files before mutation| `CREATED`, `ACTIVE`, `RESTORED`, `PRUNED` | Filesystem |
| **AuditEvent**| Tamper-evident cryptographic log of activity | `RECORDED`, `VERIFIED` | DB & JSONL |

---

## 5. Vertical Slice Implementation Strategy

To ensure continuous verification and prevent "big bang" integration failures, Phase 2 is decomposed into 5 progressive vertical slices:

```
+-------------------------------------------------------------------------+
| SLICE 1: workspace.patch (Single Text File)                             |
| - Domain models, PolicyEngine, ApprovalEngine, Atomic File Replacement  |
| - Base checksum verification, conflict detection, audit, test contracts |
+-------------------------------------------------------------------------+
                                     │
                                     v
+-------------------------------------------------------------------------+
| SLICE 2: Multi-File Patching & Transactional Consistency                |
| - Multi-file unified diffs, all-or-nothing atomicity, batch audit       |
+-------------------------------------------------------------------------+
                                     │
                                     v
+-------------------------------------------------------------------------+
| SLICE 3: Checkpoints & Reversible Recovery                              |
| - snapshot.create, snapshot.restore, rollback verification              |
+-------------------------------------------------------------------------+
                                     │
                                     v
+-------------------------------------------------------------------------+
| SLICE 4: Controlled Command Execution (execution.request)                |
| - Structured argv (no shell string), command whitelist, env sanitizing  |
| - Output streaming, timeout enforcement, process group kill             |
+-------------------------------------------------------------------------+
                                     │
                                     v
+-------------------------------------------------------------------------+
| SLICE 5: Job & Process Management                                       |
| - Durable Job state machine, process tree tracking, circuit breakers    |
| - Background execution, signal handling, resource governor budgets      |
+-------------------------------------------------------------------------+
```

---

## 6. Architecture Quality Invariants

1. **Fail-Closed Default**: Any unknown parameter, missing capability, expired approval, or evaluation error produces a structured `DENY` or `REQUIRE_APPROVAL`.
2. **Deterministic Reproducibility**: All operations are tested across CI and physical Android Termux hardware with zero hidden environment dependencies.
3. **Traceability**: Every execution result links to an `ExecutionContract`, an `Approval` (if required), and a cryptographically chained `AuditEvent`.
