# TACP Architecture Contract & Invariants Specification

This document establishes the architectural layers, module boundaries, subsystem responsibilities, and hard invariants governing the Termux AI Control Plane (TACP).

---

## 1. Subsystem Layering & Dependency Order

```text
┌────────────────────────────────────────────────────────────────────────┐
│ 1. ACCESS LAYER                                                        │
│    - McpServer (JSON-RPC 2.0 dispatch, modern & legacy protocols)      │
│    - StreamableHttpTransport (SSE, Chunked JSON, CORS, Session-Id)     │
│    - StdioTransport (Local CLI pipes)                                  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. GOVERNANCE & CONTROL LAYER                                          │
│    - TokenService (Bearer SHA-256 verification, scoping, revocation)   │
│    - PolicyEngine (TrustTier, role enforcement, rule compilation)      │
│    - LeaseEngine & ApprovalEngine (Human-in-the-loop approvals)         │
│    - RequestContext (Deadlines, cancellation tokens, trace correlation)│
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 3. CONCURRENCY & ORCHESTRATION LAYER                                   │
│    - AdmissionController (Multi-lane resource isolation: 6 lanes)      │
│    - SingleFlight (Request coalescing and stampede prevention)         │
│    - LifecycleManager (CONNECTED, DEGRADED, BACKGROUNDED, SUSPENDED)   │
│    - RequestTracer (11-phase nanosecond lifecycle accounting)          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 4. CORE SERVICES & HARDWARE ENGINE                                     │
│    - DeviceStateManager (Stratified 10-field cache: L1/L2/L3)          │
│    - WorkspaceService (Jail path validation, root mapping)             │
│    - PatchService (Optimistic concurrency, unified diffs, snapshots)   │
│    - AuditService (Tamper-evident SHA-256 linear hash chaining)        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 5. PROVIDERS & IPC BACKENDS                                            │
│    - HttpCompanionTransport (Persistent HTTP, keep-alive, circuit brk)│
│    - TermuxBackend (Direct posix/procfs, libc APIs)                    │
│    - AndroidBackend (ADB, Shizuku, Companion IPC)                      │
│    - Database (SQLite WAL, synchronous=NORMAL, 30s busy timeout)       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Fundamental Architectural Invariants

### Invariant 1: The Subprocess Elimination Rule
> Under no circumstances may an inspection or telemetry capability invoke a `/system/bin` or Termux subprocess (`pm`, `ps`, `getenforce`, `su`) on a warm cached path.
- Rationale: Fork-exec in Android 16 costs 10–35 ms per process creation.
- Enforcement: All fast hardware status must be acquired via direct `/proc` or `/sys` filesystem reads (costing 0.05–0.18 ms), or resolved from stratified TTL caches.

### Invariant 2: Bounded Lane Concurrency & Isolation
> Fast telemetry reads and health probes must NEVER queue behind long-running file mutations or slow network I/O.
- Rationale: A burst of concurrent patch mutations or remote companion timeouts must not starve agent health checks.
- Enforcement: Admission controller enforces strict isolated semaphores:
  `FAST_READ` (64 slots), `FILESYSTEM` (8 slots), `PROCESS` (4 slots), `COMPANION` (4 slots), `MEDIA` (2 slots), `MUTATION` (2 slots).

### Invariant 3: Single-Flight Cache Stampede Prevention
> When 100 concurrent requests query an expired hardware metric, exactly ONE physical refresh executes.
- Enforcement: All expensive state captures (`device.snapshot`) must execute through `SingleFlight.do()`.

### Invariant 4: Cryptographic Audit Immutability
> Every policy decision, mutation, and tool dispatch must produce an immutable `AuditEvent` linked into a cryptographically anchored SHA-256 hash chain rooted at genesis.
- Enforcement: `AuditService.record_event()` computes canonical serialized JSON hashes under atomic SQLite transactions. Integrity is strictly verifiably via `tacp audit verify`.

### Invariant 5: Fail-Fast Circuit Breaking
> When companion services fail or disconnect, subsequent dependent requests must abort in < 0.1 ms rather than blocking worker threads for 10 seconds.
- Enforcement: `HttpCompanionTransport` trips to `OPEN` after 3 consecutive errors, transitioning device lifecycle to `DEGRADED` and immediately rejecting requests with `UNAVAILABLE`.
