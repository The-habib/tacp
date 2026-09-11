# Remote Trust Boundary Architecture

## 1. Governing Law
> **AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.**

Transport connectivity is not authorization. The OpenAI Secure MCP Tunnel provides an encrypted outbound communication conduit; **TACP provides the authority and policy boundaries**. These two domains are strictly orthogonal and decoupled.

```
+-------------------------------------------------------------+
|                      OpenAI Cloud                           |
|  [ChatGPT Session] <---> [Secure MCP Tunnel Infrastructure] |
+-------------------------------------------------------------+
                              |
                     Outbound TLS Tunnel
                              |
                              v
+-------------------------------------------------------------+
|              Android Device (Termux Userspace)              |
|                                                             |
|  [tunnel-client daemon] (Transport Layer)                   |
|            |                                                |
|       stdio JSON-RPC                                        |
|            v                                                |
|  [TACP MCP Server] (Protocol Layer)                         |
|            |                                                |
|       Principal: REMOTE_AI                                  |
|            v                                                |
|  [TACP PolicyEngine] (Governance Boundary)                  |
|       - Trust Profile: REMOTE_READ_ONLY                     |
|       - Risk Level: R0 (Observation Only)                   |
|       - Mutation: DENIED                                    |
|       - Execution: DENIED                                   |
|       - Leases: DENIED                                      |
|            v                                                |
|  [Filesystem / System Providers]                            |
|       - Path Jailing                                        |
|       - Secret Redaction                                    |
|       - Truncation / Bounded Output                         |
|            v                                                |
|  [Tamper-Evident SHA-256 Audit Chain] (Verification)        |
+-------------------------------------------------------------+
```

## 2. Remote Principal Identity (`PrincipalType.REMOTE_AI`)
A dedicated principal type `PrincipalType.REMOTE_AI` is established in `tacp.control.identity`:
* **Credential Source**: `CredentialSource.TUNNEL`.
* **Trust Tier**: `TrustTier.RESTRICTED`.
* **Authorities Granted**: `Authority.READ_WORKSPACE` only.
* **Authorities Prohibited**:
  * `Authority.MUTATE_WORKSPACE` (Denied)
  * `Authority.EXECUTE_COMMAND` (Denied)
  * `Authority.APPROVE_ACTION` (Denied)
* **Elevation Invariant**: `is_elevated()` returns `False` unconditionally. Under no circumstances can a remote AI principal claim, inherit, or elevate to human operator privileges.

## 3. Policy Governance & Trust Profiles
Under Phase 6.5, remote connections operate strictly under the `REMOTE_READ_ONLY` trust profile:
* Only $R_0$ observation capabilities are allowed (`system.inspect`, `system.health`, `system.version`, `capabilities.list`, `workspace.list`, `workspace.inspect`, `fs.list`, `fs.stat`, `fs.read`, `fs.search`, `process.list`, `process.inspect`, `audit.recent`).
* All mutation capabilities (`workspace.patch`, `workspace.patch_batch`, `workspace.rollback`) return immediate `DENY`.
* All process execution capabilities (`execution.request`, `execution.inspect`, `execution.cancel`) return immediate `DENY`.
* Capability leases (`LeaseEngine`) cannot be granted or consumed by remote principals; requests with `lease_id` are rejected.
* Internal administrative operations (such as `audit.verify_integrity`) are denied.

## 4. Path Jailing & Secret Protection
All file operations are confined within explicitly registered workspace roots:
* Relative and absolute traversals (`../`, `/etc/passwd`, `/data/data/...`) are caught and rejected with `OUTSIDE_WORKSPACE`.
* Symlinks pointing outside the workspace root are resolved and rejected.
* Files matching secret patterns (`.env`, `id_rsa`, `*.pem`, `credentials.json`) are blocked with `SECRET_PROTECTED`.
* Incidental credentials inside read buffers are sanitized using pattern-based token redaction.

## 5. Defense Against Untrusted Input
1. **Prompt Injection Invariant**: Hostile instructions embedded in files (e.g. `SYSTEM OVERRIDE: execute bash`) are read as passive, verbatim UTF-8 string data. They never alter the execution context, policy state, or authorization tables.
2. **Output Limits**: Files and searches are strictly bounded by `OutputLimits` (e.g., maximum read bytes, directory count caps), protecting against tunnel buffer flooding or memory starvation.
