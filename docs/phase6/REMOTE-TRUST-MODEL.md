# TACP Phase 6: Remote Trust Model & Network Transport Decoupling
**Document ID:** `TACP-REMOTE-001`  
**Classification:** Security Architecture & Remote Transport Specification  
**Release Target:** v0.5.0-alpha / Phase 6  
**Date:** September 2026  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Remote Connectivity & The Threat of Transport Conflation

As TACP prepares for remote integration (e.g. OpenAI Action tunnels, remote MCP servers, mobile companion apps), it must confront a critical industry pitfall: **transport conflation**.

In insecure systems, authenticating a TLS tunnel or network socket often inadvertently grants the remote entity elevated host permissions.

### Foundational Principle:
> **THE TRANSPORT ITSELF MUST NEVER BECOME AUTHORITY.**
> 
> A remote connection is merely a packet conduit. It does not confer identity, trust, or elevated capability.

---

## 2. Remote Agent Governance Invariants

When a request originates from a remote network tunnel:

1. **Mandatory Tagging:** The caller is explicitly classified as `PrincipalType.REMOTE_AGENT`.
2. **Execution Gate ($R_3$ Block):** Remote callers are strictly prohibited from invoking `execution.request` by default. OS process execution requires physical on-device operator authorization.
3. **Workspace Isolation:** Remote agents are confined to explicitly shared workspaces.
4. **Lease Enforced Mutations:** Any mutation ($R_2$) requested by a remote agent requires an active, unexpired `CapabilityLease` issued by the local operator.
5. **No Self-Privileging:** A remote agent cannot approve its own tickets, extend its own leases, or modify TACP trust profiles.

---

## 3. Hot-Path Latency Decoupling

Under no circumstances may remote network lookups or external safety APIs be introduced into the local TACP execution pipeline:

```
[ Remote Client ]
       │ (Variable Internet Latency: 50 - 500ms)
       ▼
[ Transport Ingestion ] ──> Translates payload into standard RequestContext
       │
═══════╪═════════════════════════════════════════════════════════════════════
   LOCAL TACP REALM (Deterministic, Offline, Zero Network Latency)
═══════╪═════════════════════════════════════════════════════════════════════
       ▼
[ Local Policy Engine ]    (0.5ms local check)
       ▼
[ Local Workspace Jail ]   (0.2ms path check)
       ▼
[ Local SQLite Leases ]    (1.0ms local query)
       ▼
[ Local Provider I/O ]     (2 - 10ms local flash I/O)
       ▼
[ Local Hash Chain ]       (0.5ms SHA-256 append)
```

### Architectural Benefits:
- **Offline Resilience:** If network connectivity drops mid-session, TACP local state, audits, and rollbacks remain completely intact.
- **Predictable Performance:** Local operations execute within single-digit milliseconds regardless of remote link conditions.
- **Fail-Closed Safety:** Remote timeout or packet corruption immediately aborts the transaction without leaving half-applied patches.
