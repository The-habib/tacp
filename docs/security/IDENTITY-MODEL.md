# TACP Identity & Principal Architecture

**Document:** `docs/security/IDENTITY-MODEL.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**Security Lead:** Antigravity Principal Security Engineer  
**Date:** September 11, 2026  

---

## 1. Identity Principles

A core failure mode of early agentic systems is conflating **caller claims** with **authenticated identity**. In TACP:
1. **Who Requested != What They Are Allowed To Do**: Identity establishes provenance; Policy establishes authority.
2. **Caller Claims Are Untrusted**: A request payload asserting `{"principal": "admin"}` is untrusted data. Identity must be established by cryptographic or transport credentials verified at the trusted Access Plane boundary.
3. **Immutability of Context**: Once established at the boundary, a request's `RequestContext` and `Principal` cannot be altered as it flows through the execution pipeline.

---

## 2. The 5 Principal Types

Every interaction with TACP is associated with an authenticated `Principal` belonging to one of five explicit types:

| Principal Type | Actor Description | Authentication Method | Default Trust Level | Autonomy Ceiling |
|---|---|---|---|---|
| **HUMAN** | The device owner / CEO operating via local CLI or verified dashboard | Local Unix user credentials / hardware biometric | High | `L5` (Privileged) |
| **AI_AGENT** | Autonomous LLM agent interacting via MCP or tunnel | Session bearer token / pre-shared tunnel key | Restricted | `L3` (Workspace) |
| **SYSTEM** | TACP internal background services (e.g. log rotation, health checks) | Cryptographically signed internal daemon token | Trusted | `L4` (Extended) |
| **SCHEDULED_JOB** | Cron or periodic jobs configured by the user | Job execution ticket bound to job configuration | Constrained | `L2` (Low-risk) |
| **LOCAL_OPERATOR** | Interactive developer typing in a Termux subshell | Termux process UID / GID verification (`u0_a316`)| High | `L4` (Extended) |

---

## 3. The Principal Entity & Schema

```sql
CREATE TABLE IF NOT EXISTS principals (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK(type IN ('HUMAN', 'AI_AGENT', 'SYSTEM', 'SCHEDULED_JOB', 'LOCAL_OPERATOR')),
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'SUSPENDED', 'REVOKED')),
    autonomy_ceiling TEXT NOT NULL DEFAULT 'L2',
    credentials_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_authenticated_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_principals_status ON principals(status);
```

### In-Memory Principal Class Definition
```python
@dataclass(frozen=True)
class Principal:
    id: str
    type: PrincipalType
    name: str
    status: PrincipalStatus
    autonomy_ceiling: AutonomyLevel
    token_fingerprint: str
    created_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        return self.status == PrincipalStatus.ACTIVE
```

---

## 4. Identity Resolution Pipeline

```
[Inbound Request (MCP / CLI)]
             │
             v
[Token Extraction]          --> Extracts Bearer Token or Session Cookie from headers/args
             │
             v
[Cryptographic Verification] --> Hashes token and queries 'principals' table
             │
             ├── If Token Invalid / Expired: Fail-closed with ErrorCode.NOT_AUTHORIZED
             │
             v
[Status Check]               --> Asserts principal.status == 'ACTIVE'
             │
             ├── If Suspended / Revoked: Fail-closed with ErrorCode.PRINCIPAL_SUSPENDED
             │
             v
[Context Binding]            --> Generates immutable RequestContext:
                                 - principal: Principal
                                 - trace_id: UUIDv4
                                 - session_id: str
                                 - issued_at: monotonic timestamp
```

---

## 5. Security & Boundary Invariants

1. **No Anonymous Execution**: Anonymous requests are restricted strictly to read-only discovery (`server/discover`, `system.version`, `ping`). Any mutating or executing tool call with an anonymous principal fails immediately.
2. **Cross-Principal Isolation**: An agent principal cannot inspect, cancel, or modify jobs or leases owned by another principal unless explicitly granted administrative delegation by a `HUMAN` principal.
3. **Session Expiry**: Agent principal sessions expire after a configurable duration (default: 8 hours). Expired sessions require re-authentication.
4. **Audit Immutability**: The authenticated `principal.id` is permanently burned into the cryptographic `AuditEvent` record for every executed action.
