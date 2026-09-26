# TACP Security & Governance Architecture

## 1. Threat Model for Remote Mobile MCP

Running a Model Context Protocol (MCP) server on an Android device introduces unique security considerations:
- Mobile devices store private personal data, app sandbox state, photos, SMS, and authentication credentials.
- Remote AI models may experience hallucinations, prompt injection, or autonomous runaway tool-call loops.
- Cellular carrier networks employ Carrier-Grade NAT (CGNAT), complicating inbound connections and tempting insecure open-tunnel practices.

TACP addresses these risks through **defense-in-depth, zero-trust invariants, strict sandboxing, and immutable audit trails**.

```
+---------------------------------------------------------------------------------+
|                                Remote AI Agent                                  |
+---------------------------------------------------------------------------------+
                                        |  1. Bearer Token (tacp_sec_***)
                                        v
+---------------------------------------------------------------------------------+
| Barrier 1: Cryptographic Authentication (SHA-256 hash lookup in SQLite)         |
+---------------------------------------------------------------------------------+
                                        |  2. Token Scopes Validated
                                        v
+---------------------------------------------------------------------------------+
| Barrier 2: Capability & Policy Engine (Default-Deny, Trust Profile Check)       |
+---------------------------------------------------------------------------------+
                                        |  3. Path & Target Containment
                                        v
+---------------------------------------------------------------------------------+
| Barrier 3: Filesystem Jailing (Registered Workspace Root Boundary Verification) |
+---------------------------------------------------------------------------------+
                                        |  4. Execution Governance
                                        v
+---------------------------------------------------------------------------------+
| Barrier 4: Zero-Shell Execution Boundary (shell=False, setsid, Watchdogs)       |
+---------------------------------------------------------------------------------+
                                        |  5. SHA-256 Cryptographic Chaining
                                        v
+---------------------------------------------------------------------------------+
| Barrier 5: Tamper-Evident Audit Logging (Immutable SQLite Event Store)          |
+---------------------------------------------------------------------------------+
```

---

## 2. Authentication & Credential Architecture

### 2.1 Token Format and Storage Invariants
- Tokens are generated using the OS cryptographically secure random number generator (`secrets.token_hex(32)`).
- Full Token Format: `tacp_sec_<64_hex_characters>`
- **Plaintext Storage Invariant**: The raw bearer token is returned **exactly once** to the operator at creation time.
- The token is hashed with SHA-256 before insertion into the `auth_tokens` database table.
- Incoming HTTP requests present `Authorization: Bearer tacp_sec_...`. The server computes `SHA-256(received_token)` and queries the database for an exact hash match. Even if the database file is compromised, raw bearer tokens cannot be derived.

### 2.2 Scopes Hierarchy

| Scope | Authority Granted | Subsumes |
|---|---|---|
| `tacp.read` | Global read: system telemetry, workspace file reading, audit inspection | `tacp.files.read`, `tacp.system.read`, `tacp.process.read` |
| `tacp.files.read` | Read files inside registered workspaces | None |
| `tacp.files.write` | Atomic unified diff patch application inside registered workspaces | None |
| `tacp.system.read` | Device diagnostics, battery, memory, Android release info | None |
| `tacp.process.read` | Process tree inspection and listing | None |
| `tacp.execute` | Controlled command execution (requires feature flag + human approval) | None |
| `tacp.admin` | Full superuser access to all capabilities and administrative controls | All scopes |

---

## 3. Filesystem Jailing & Path Containment

TACP enforces strict containment within explicitly registered workspaces (e.g. `termux-home` or `phone-storage`).

### Invariants:
1. **Canonical Root Containment**: Every target path is resolved using `.resolve()` and compared against the workspace root. If `resolved_target` does not start with `workspace.root_path`, the request is denied immediately.
2. **Path Traversal Prevention**: Any request containing `..` or leading slashes attempting relative breakout is rejected at the policy layer before filesystem I/O occurs.
3. **Protected Resource Blocklist**: Even inside registered workspaces, access to the following is hardcoded denied:
   - `.git` directories and objects
   - `.tacp` metadata and SQLite database files (`tacp.db`)
   - Sensitive credential files (`.env`, `*id_rsa*`, `*id_ed25519*`)
4. **Symlink Boundary Checks**: Symlinks pointing outside the workspace root are detected and blocked.

---

## 4. Governed Command Execution Boundary

To prevent unauthorized shell execution or arbitrary remote code execution:

1. **Zero-Shell Execution (`shell=False`)**:
   - TACP never executes commands through `/bin/sh`, `/bin/bash`, or `cmd.exe`.
   - All executions invoke binaries directly using `os.execve` / `subprocess.Popen` with explicit `argv` lists.
   - Shell metacharacters (`;`, `|`, `&`, `>`, `<`, `` ` ``, `$()`) have zero effect because shell interpretation is completely bypassed.
2. **Process Session Isolation**:
   - Child processes run in isolated process groups via `preexec_fn=os.setsid`.
   - Process termination cleanly kills the entire process group, preventing orphaned processes.
3. **Hermetic Environment**:
   - Environment variables are scrubbed; only an explicit safe allowlist is inherited.
   - Secrets and tokens are never exposed in environment variables.
4. **Execution Watchdogs & Output Scrubbing**:
   - Hard execution timeouts kill runaway processes.
   - All stdout/stderr is stripped of ANSI escape sequences before returning to AI models.
5. **Interactive Human Approval & Emergency Stop**:
   - High-risk commands require explicit human approval via interactive ticket or CLI verification.
   - The operator can run `tacp execution emergency-stop` at any time to immediately kill all running processes.

---

## 5. Tamper-Evident SHA-256 Audit Chain

All TACP events (token creation, policy decisions, workspace reads, mutations, and command executions) are recorded in an append-only SQLite table with cryptographic chaining:

$$\text{hash}_n = \text{SHA-256}(\text{hash}_{n-1} \parallel \text{timestamp}_n \parallel \text{capability}_n \parallel \text{principal}_n \parallel \text{parameters}_n)$$

To verify that the audit log has not been tampered with or modified:
```bash
tacp audit verify
```
Output:
```
========================================
 TACP Cryptographic Audit Verification  
========================================
Records Verified : 48
Chain Status     : VALID
Genesis Hash     : a1b2c3d4e5f6...
Head Hash        : 9f8e7d6c5b4a...
Result           : Tamper-evident integrity verified successfully.
========================================
```
