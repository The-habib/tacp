# TACP Phase 5: Identity and Authority Model
**Document ID:** `TACP-ID-AUTH-001`  
**Classification:** Control Plane Security Architecture  
**Release Target:** v0.4.0-rc.1 Hardening / Phase 5  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Architectural Mandate: No Privilege by Name

Prior to Phase 5, certain parts of the policy engine inspected `principal.id` (e.g. `if principal.id in ("operator", "human_operator"): allow`).
This is a critical security violation. A principal's identifier is an identity label, **never** an authority grant.

Phase 5 enforces:
> **A principal's name MUST NOT itself confer privilege.**
> Privileges, capabilities, and approval exemptions must derive strictly from `TrustTier`, `PrincipalType`, and explicit `Authority` sets.

---

## 2. Formal Identity Taxonomy

### 2.1 Principal Types (`PrincipalType`)
- `AGENT`: Autonomous software actor (e.g. LLM worker, MCP client, background subagent). Subject to strict capability gating, workspace boundaries, and mandatory human approval for mutations.
- `HUMAN`: Real human operator communicating over local interactive TTY.
- `SYSTEM`: Internal TACP engine maintenance process (e.g. migration runner, audit chain verifier, crash recovery).
- `SERVICE`: Local Unix daemon or sidecar process.

### 2.2 Trust Tiers (`TrustTier`)
- `UNTRUSTED`: Zero mutation capabilities, read-only inspection only with rate limiting.
- `RESTRICTED`: Standard operating tier for AI agents. Governed mutation permitted only with explicit human approval.
- `PRIVILEGED`: Elevated operational tier for verified human operator and internal system maintenance. Can issue approvals and initiate emergency stops.

### 2.3 Explicit Authorities (`Authority`)
- `read:workspace`: Authority to inspect files and listing directory contents.
- `mutate:workspace`: Authority to request filesystem patches.
- `execute:command`: Authority to request controlled OS process execution (`printf`, `echo`, `true`).
- `execute:dangerous`: Authority to request high-risk or destructive actions.
- `approve:action`: Authority to grant approval tickets.
- `revoke:action`: Authority to revoke approvals or abort operations.
- `admin:emergency_stop`: Authority to invoke global emergency process termination.
- `view:audit`: Authority to read complete tamper-evident audit history.
- `operator:rollback`: Authority to execute workspace snapshots and batch rollbacks without additional approval.

---

## 3. Request Context & Binding

Every capability invocation generates an immutable `RequestContext`:
- `capability`: The requested capability name (e.g. `execution.request`).
- `principal`: The calling `Principal` structure with its validated credentials, role, trust tier, and authority set.
- `request_id`: Unique UUIDv4 tracking the lifecycle of the request.
- `trace_id`: Distributed tracing identifier linking subagent invocations.
