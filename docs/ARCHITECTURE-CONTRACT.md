# TACP Architecture Contract & Subsystem Boundaries

## 1. Architectural Philosophy
TACP (Termux AI Control Plane) is engineered as an agent-agnostic, low-overhead, high-security bridge between remote AI agents and physical Android devices. To prevent architectural decay, spaghetti coupling, and security bypasses, every component resides in a strictly delineated architectural layer.

---

## 2. Layer Hierarchy & Strict Boundaries

```
[ Remote AI / MCP Client ]
          │ (JSON-RPC over Streamable HTTP / stdio)
          ▼
┌───────────────────────────────────────────────┐
│ 1. TRANSPORT LAYER                            │
│    - HTTP/1.1 with Keep-Alive & Bounded Pools │
│    - stdio Pipe Transport                     │
│    - Backpressure (32 concurrency cap)        │
└───────────────────────┬───────────────────────┘
                        ▼
┌───────────────────────────────────────────────┐
│ 2. MCP PROTOCOL LAYER                         │
│    - JSON-RPC 2.0 framing & validation        │
│    - Protocol versioning (2026-07-28)         │
│    - Tool schemas & resource dispatch         │
└───────────────────────┬───────────────────────┘
                        ▼
┌───────────────────────────────────────────────┐
│ 3. IDENTITY & AUTHENTICATION                  │
│    - Bearer Token validation (SHA-256)        │
│    - Principal creation & Scope binding       │
│    - Generation-cached token resolution       │
└───────────────────────┬───────────────────────┘
                        ▼
┌───────────────────────────────────────────────┐
│ 4. POLICY GOVERNANCE (Zero Trust)             │
│    - Trust Profiles: LOCKDOWN, BALANCED, PRO  │
│    - Risk Tiers: R0 (observe) to R3 (exec)    │
│    - Approval token verification              │
└───────────────────────┬───────────────────────┘
                        ▼
┌───────────────────────────────────────────────┐
│ 5. CAPABILITY & RESOLUTION ENGINE             │
│    - O(1) CapabilityIndex & ProviderIndex     │
│    - ProviderState: AVAILABLE, DEGRADED, etc. │
│    - Least-privilege backend binding          │
└───────────────────────┬───────────────────────┘
                        ▼
┌───────────────────────────────────────────────┐
│ 6. SERVICE ORCHESTRATION                      │
│    - WorkspaceService (jail enforcement)      │
│    - ExecutionService (16-stage pipeline)     │
│    - PatchService (atomic filesystem diffs)   │
│    - DeviceStateManager (stratified TTL)      │
└───────────────────────┬───────────────────────┘
                        ▼
┌───────────────────────────────────────────────┐
│ 7. PROVIDER & IPC LAYER                       │
│    - FilesystemProvider (canonical jail)      │
│    - ProcessExecutor (setsid, pipe watchdog)  │
│    - CompanionTransport (persistent HTTP IPC) │
│    - Termux/Android native probes             │
└───────────────────────┬───────────────────────┘
                        ▼
┌───────────────────────────────────────────────┐
│ 8. PERSISTENCE & AUDIT                        │
│    - SQLite WAL (`Database` thread-local)     │
│    - AuditService (cryptographic SHA-256 chain)│
│    - Cooperative group commit                 │
└───────────────────────────────────────────────┘
```

---

## 3. Strict Boundary Rules

1. **Transport Isolation:** Transport handlers (`StreamableMcpHandler`) MUST NOT execute business logic, manipulate filesystem paths, or query SQLite directly. All requests must route through `McpServer` and `McpToolRegistry`.
2. **Authentication Before Dispatch:** No tool execution or resource read (except `/health` and `/ready`) may execute without a resolved `Principal`.
3. **Policy Gate Invariant:** Every capability execution MUST pass through `PolicyEngine.evaluate_request()`. No provider or service may be called directly without policy approval.
4. **Path Jailing Invariant:** All filesystem mutations and inspections MUST resolve paths through `_resolve_in_jail()`. Path traversal attempts (`..`, null bytes, symlink escape) must immediately raise `TacpSecurityError`.
5. **Audit Invariant:** Every mutating action (`workspace.patch`, `workspace.rollback`, `execution.request`) and policy denial MUST produce an immutable, tamper-evident `AuditEvent` linked into the cryptographic hash chain.
6. **Subprocess Governance:** Raw shell string execution (`shell=True`, `bash -c`) is forbidden. Commands must be executed via `ProcessExecutor` with discrete argument vectors, session isolation (`setsid`), and runtime timeouts.
7. **Companion Decoupling:** Companion APK interactions must use `CompanionTransport`. Capabilities must not hardcode HTTP client calls or raw socket addresses.
