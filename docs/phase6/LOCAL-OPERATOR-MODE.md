# TACP Phase 6: Local Operator Mode & Identity Hierarchy
**Document ID:** `TACP-ID-OP-001`  
**Classification:** Identity Architecture & Access Control Specification  
**Release Target:** v0.5.0-alpha / Phase 6  
**Date:** September 2026  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. The Need for Distinct Operational Contexts

In a local-first system like Termux AI Control Plane, treating all callers as identical creates severe security failure modes:
1. If the local human operator is treated like an untrusted AI agent, the human cannot perform administrative recovery without being blocked by agent guardrails.
2. If an AI agent running inside Termux is granted human operator status, it gains sovereignty and can bypass policy.
3. If a remote client connecting over a network tunnel inherits the local human's privileges, remote prompt injection directly results in host compromise.

TACP Phase 6 establishes four mutually exclusive operational identity classes.

---

## 2. Four Operational Identity Classes

```
                  ┌───────────────────────────────┐
                  │          SYSTEM               │
                  │ (Internal Control Plane Only) │
                  └──────────────┬────────────────┘
                                 │
                  ┌──────────────┴────────────────┐
                  │       LOCAL_HUMAN             │
                  │  (Interactive Termux Shell)   │
                  └──────────────┬────────────────┘
                                 │
                  ┌──────────────┴────────────────┐
                  │       LOCAL_AGENT             │
                  │   (Local MCP Client / Sidecar)│
                  └──────────────┬────────────────┘
                                 │
                  ┌──────────────┴────────────────┐
                  │       REMOTE_AGENT            │
                  │ (OpenAI Tunnel / Network MCP) │
                  └───────────────────────────────┘
```

### Identity Class Specifications:

| Class | Transport / Origin | Capabilities Permitted | Risk Ceiling | Approval Role |
|---|---|---|---|---|
| **`SYSTEM`** | In-process daemon / CLI init | Internal migrations, orphan cleanup | $R_5$ | Self-contained / Internal |
| **`LOCAL_HUMAN`** | Interactive TTY (`/dev/pts/*`) | All capabilities, policy edits, approvals | $R_5$ | Approver (Can issue tickets & leases) |
| **`LOCAL_AGENT`** | Unix domain socket / local stdio | $R_0$ (automatic), $R_1-R_3$ (via lease/ticket) | $R_3$ | Requester (Must seek human approval for $R_2/R_3$) |
| **`REMOTE_AGENT`** | Network socket / Tunnel | $R_0$ (automatic), $R_1-R_2$ (via strict lease) | $R_2$ (Execution blocked) | Requester (Cannot approve; execution denied) |

---

## 3. Zero Name Privilege & Anti-Spoofing

An agent cannot claim to be `LOCAL_HUMAN` merely by supplying `principal_id: "operator"` or `principal_id: "human"`.

TACP enforces:
1. **Transport-Bound Identity:** Requests arriving over network sockets or standard MCP pipes are tagged with `PrincipalType.AGENT` or `PrincipalType.REMOTE`.
2. **Authority Token Verification:** `LOCAL_HUMAN` status requires possession of an active session credential or direct TTY origin.
3. **Downstream Enforcement:** The policy engine checks `principal.has_authority(Authority.OPERATOR_ROLLBACK)` rather than matching string names.

---

## 4. Local Operator CLI Commands

The local human operator uses dedicated CLI tools to supervise agents:
```bash
tacp approvals list              # View pending approval tickets
tacp approvals approve <token>   # Grant approval for a bounded plan
tacp lease list                  # View active capability leases
tacp lease revoke <lease_id>     # Immediately cancel an active lease
tacp profile set STRICT          # Increase governance posture
tacp emergency-stop              # Instantly terminate all active execution
```
