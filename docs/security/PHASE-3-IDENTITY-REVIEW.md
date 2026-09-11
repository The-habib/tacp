# TACP Phase 3 — Identity & Principal Architecture Review
## Caller Authentication, Trust Tiers, and Authority Delegation

- **Date:** September 11, 2026
- **Release:** `v0.3.0-rc.1` / `v0.3.0rc1`
- **Module:** `src/tacp/control/identity.py`
- **Security Boundary:** Pre-Shell / Pre-Android / Pre-Network Security Gate
- **Status:** **RATIFIED**

---

## 1. Executive Summary

This security review formalizes the identity, principal binding, and authority delegation model for TACP. In prior vertical slices (Phase 1 through Phase 2.5), TACP operated primarily in a single-process or local stdio environment where MCP requests were implicitly treated as originating from a local agent (`Principal(id="mcp-client", role="agent")`). 

As TACP prepares for controlled command execution, remote access protocols, and OpenAI Secure MCP Tunnel integration, **caller-supplied claims can no longer be accepted without cryptographic verification**.

### The Cardinal Axiom of Identity
> **CALLER-SUPPLIED DATA MUST NEVER BECOME TRUSTED AUTHORITY WITHOUT INDEPENDENT VALIDATION.**
> 
> A caller cannot elevate its privilege simply by passing `principal_id="admin"`, `role="operator"`, or `authenticated=True` in request metadata, JSON-RPC arguments, or HTTP headers.

---

## 2. Principal & Trust Model Taxonomy

`src/tacp/control/identity.py` formalizes the following dimensions:

### 2.1 Principal Types (`PrincipalType`)
1. **`AGENT`**: Autonomous or semi-autonomous AI models and tools operating on behalf of an end-user or orchestrator. Agents operate under default-deny boundaries and must always request human approval for mutating or high-risk operations.
2. **`HUMAN`**: Verified human operator. Capable of approving tickets, initiating manual rollbacks, and authorizing policy overrides within configured boundaries.
3. **`SYSTEM`**: Internal TACP background tasks, health monitors, or kernel-level recovery mechanisms executing within the trusted core boundary.

### 2.2 Trust Tiers (`TrustTier`)
1. **`UNTRUSTED`**:
   - Callers whose origin is unverified or external.
   - Strictly restricted to public discovery endpoints (`server/discover`, `ping`, `system.version`).
   - Zero access to filesystem reads, system inspection, or mutation.
2. **`RESTRICTED` (Default for Local MCP Clients)**:
   - Callers communicating over authenticated local channels (e.g., local stdio within Termux).
   - Permitted read-only workspace and system queries within jail boundaries.
   - Forbidden from mutating operations unless explicitly authorized via a valid, unconsumed human approval ticket.
3. **`PRIVILEGED`**:
   - Fully verified local operators or cryptographically proven administrators.
   - Authorized to grant approvals, configure policy engines, and execute governed mutations.

### 2.3 Credential Sources (`CredentialSource`)
1. **`LOCAL_STDIO`**: Inherent boundary of the OS process running in Termux. Standard input/output is governed by Linux UID/GID boundaries.
2. **`TOKEN`**: Cryptographically verified bearer token or mutual TLS client certificate (for network transports).
3. **`SYSTEM`**: In-process invocation by TACP core components.
4. **`NONE`**: Unauthenticated caller (e.g., discovery probes).

---

## 3. Caller Transport Models

```
+-------------------------------------------------------------------------------+
|                             CALLER TRANSPORT MODELS                           |
+-------------------------------------------------------------------------------+
| 1. LOCAL STDIO (Current)                                                      |
|    Termux User Shell ---> Stdio Pipes ---> TACP MCP Adapter                   |
|    Identity: Principal(id="mcp-client", type=AGENT, tier=RESTRICTED)          |
|    Authority: Bounded by Linux UID sandbox; Requires Human Approval Ticket.   |
+-------------------------------------------------------------------------------+
| 2. OPENAI SECURE MCP TUNNEL (Future Phase)                                    |
|    OpenAI Client ---> WebSocket / TLS ---> Local Tunnel Client ---> Stdio     |
|    Identity: Cryptographically proven OpenAI Workspace Principal               |
|    Authority: Validated via Tunnel handshake; Restricted Tier by default.     |
+-------------------------------------------------------------------------------+
| 3. REMOTE ACCESS / NETWORK API (Future Phase)                                 |
|    Remote Agent ---> HTTP/SSE or WS ---> TACP Ingress Adapter                 |
|    Identity: Bearer Token / HMAC-SHA256 Auth / Principal Binding Registry     |
|    Authority: Explicitly bound to registered public keys; NEVER caller-claimed.|
+-------------------------------------------------------------------------------+
```

### 3.1 Model 1: Trusted Local Caller (Current Baseline)
- **Transport:** Standard input / standard output (`stdin`/`stdout`).
- **OS Boundary:** Android Linux UID/GID (Termux user `u0_aXXX`).
- **Identity Assignment:** The MCP adapter assigns `Principal.local_agent("mcp-client")`.
- **Trust Assumption:** The caller has access to the local shell, but is constrained by TACP's application policy engine. Mutating operations (`workspace.patch`, `workspace.patch_batch`) reject execution until a human operator approves the ticket via the CLI or direct database interaction.

### 3.2 Model 2: OpenAI Secure MCP Tunnel (Readiness Baseline)
- **Transport:** Outbound encrypted WebSocket or TLS connection initiated by the local operator via the official OpenAI Tunnel client.
- **Trust Boundary:** The tunnel client runs locally in Termux. Incoming requests from OpenAI ChatGPT or Agents pass through the tunnel interface to TACP's local transport.
- **Identity Assignment:**
  - The tunnel transport authenticates the connection with the OpenAI platform.
  - TACP assigns the request a Principal of `type=AGENT, trust_tier=RESTRICTED, credential_source=TOKEN`.
  - The request CANNOT claim `trust_tier=PRIVILEGED` or `type=HUMAN`.
  - All mutating capabilities require an out-of-band human approval granted by the local operator.

### 3.3 Model 3: Remote Network Caller (Future Design Constraint)
- Any network listener (HTTP/SSE, TCP, WebSocket) MUST enforce:
  1. Mutual authentication (mTLS or pre-shared HMAC bearer tokens).
  2. Principal binding performed at the server-side ingress layer by looking up the token hash in an authorization database.
  3. Strict rejection of incoming `X-Principal-ID`, `X-Trust-Tier`, or JSON-RPC metadata claims attempting to override server-derived principal state.

---

## 4. Request Metadata and Correlation Architecture

To satisfy **Section 22 (Request Context)**, all invocations must propagate immutable traceability context across all layers:

```python
@dataclass(frozen=True)
class RequestContext:
    capability: str
    principal: Principal
    request_id: str  # Traceable across MCP, Service, Policy, and Audit
    trace_id: str  # Distributed tracing correlation
    metadata: Dict[str, Any]  # Non-authoritative contextual telemetry
```

### 4.1 Request ID Propagation Invariant
- If an MCP client sends a JSON-RPC request ID (or an MCP 2026-07-28 `_meta.progressToken` / correlation ID), the MCP adapter binds this ID directly to `RequestContext.request_id`.
- Lower service layers (`PatchService`, `AuditService`, `LockService`) **MUST NOT** generate new, disconnected request IDs for the primary operation.
- Every audit log entry and database record emitted during the lifecycle of the request records the authoritative `request_id`.

---

## 5. Security Invariant Checklist for Identity

- [x] `Principal` dataclass distinguishes `id`, `type`, `role`, `trust_tier`, `authenticated`, `credential_source`, and `metadata`.
- [x] Factory helpers (`anonymous()`, `local_agent()`, `human_operator()`, `system()`) enforce least privilege by default.
- [x] Unauthenticated callers default to `trust_tier=UNTRUSTED`.
- [x] Local MCP stdio callers default to `trust_tier=RESTRICTED` (cannot mutate without approval).
- [x] Human approval verification requires `trust_tier=PRIVILEGED` or verified operator credentials.
- [x] Client-provided metadata dictionaries are treated as untrusted data and strictly sanitized before logging.
