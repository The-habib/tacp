# TACP Phase 6.5 Remote Integration Report: OpenAI Secure MCP Tunnel

## 1. Executive Summary & Verdict
* **Release Family**: TACP `v0.5.1-rc.1` (Phase 6.5)
* **Target Objective**: Secure end-to-end integration between ChatGPT and TACP running locally in Termux on Android via the official OpenAI Secure MCP Tunnel (`tunnel-client`).
* **Operational Mode**: Strictly **READ-ONLY OBSERVATION** (`REMOTE_READ_ONLY` trust profile, $R_0$ risk tier).
* **Verdict**: **READY WITH LIMITATIONS** (Ready for governed read-only observation; remote mutation and process execution remain strictly forbidden).

## 2. Target Architecture
```
[ChatGPT Custom Connector]
            |
(Encrypted Outbound TLS Pipe)
            v
[OpenAI Secure MCP Tunnel Infrastructure]
            |
(Outbound WebSocket / HTTP Connection)
            v
[tunnel-client daemon] (Local Go executable, v0.0.14, aarch64)
            |
(Local Stdio Pipe JSON-RPC 2.0)
            v
[TACP MCP Server] (Python 3.14.6 in Termux userspace)
            |
(Identity Bound: PrincipalType.REMOTE_AI, TrustTier.RESTRICTED)
            v
[TACP PolicyEngine] (Trust Profile: REMOTE_READ_ONLY)
    - Enforces fail-closed posture
    - Rejects all mutating & execution capabilities
    - Denies lease allocation & consumption
            v
[Filesystem & System Providers]
    - Path Jailing & Symlink Boundaries
    - Secret File Blocking & Pattern Redaction
    - Output Limits & Response Truncation
            v
[Tamper-Evident SHA-256 Audit Log] (SQLite WAL)
```

## 3. Official Tunnel Client Verification
* **Source**: Official OpenAI upstream repository (`https://github.com/openai/tunnel-client/releases/tag/v0.0.14`).
* **Binary Artifact**: `tunnel-client-v0.0.14-linux-arm64.zip`.
* **Verified SHA-256**: `2de3fb879a18edb847e0313592c912f1983685488290a7fdba7ac403e6a4fb0a`.
* **Binary Type**: Statically linked ARM64 Linux executable with zero dynamic glibc/musl requirements.
* **Physical Hardware Execution**: Runs natively on Android 13 Termux `aarch64` without proot, chroot, or emulation.

## 4. Authentication & Credential Model
* **Segregation of Authority**:
  * `OPENAI_ADMIN_KEY`: Restricted strictly to tunnel provisioning/de-provisioning. Never exposed to `tunnel-client run` or persistent daemons.
  * `CONTROL_PLANE_TUNNEL_ID`: Public tunnel identifier.
  * `CONTROL_PLANE_API_KEY`: Runtime secret provided via environment variable. Masked in all logs, status screens, and reports.
* **Zero Disk Persistence**: Credentials are never written to SQLite database tables.

## 5. Remote Trust Model & Identity
* **Governing Principle**: *"AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN."*
* **Principal Representation**:
  * Type: `PrincipalType.REMOTE_AI`.
  * Source: `CredentialSource.TUNNEL`.
  * Elevation: `is_elevated()` is hardcoded `False`. Under no circumstances can a remote AI inherit `LOCAL_HUMAN` operator capabilities.
  * Leases: Capability leasing is prohibited for remote callers.

## 6. Remote Trust Profile: REMOTE_READ_ONLY
* Active profile for remote connections: `REMOTE_READ_ONLY`.
* Only $R_0$ read-only capabilities are allowed.
* `workspace.patch`, `workspace.patch_batch`, and `execution.request` return immediate `DENY`.
* Fail-Closed Invariant: If `TACP_REMOTE_ENABLED` is false, all incoming remote calls are rejected unconditionally.

## 7. Tool Exposure & Discovery
Dynamic tool filtering exposes exactly 13 read-only tools:
1. `system.inspect`
2. `system.health`
3. `system.version`
4. `capabilities.list`
5. `workspace.list`
6. `workspace.inspect`
7. `fs.list`
8. `fs.stat`
9. `fs.read`
10. `fs.search`
11. `process.list`
12. `process.inspect`
13. `audit.recent`

All mutation, execution, and admin tools (`workspace.patch`, `execution.request`, `audit.verify_integrity`) are completely absent from `tools/list`.

## 8. Security & Adversarial Verification
A comprehensive suite of 12 adversarial tests (`tests/security/test_remote_security.py`) confirmed:
* **Secret Defense**: `.env`, `id_rsa`, and `credentials.json` are blocked with `SECRET_PROTECTED`.
* **Path Boundaries**: Relative traversals (`../../../etc/passwd`), absolute path escapes, and escaping symlinks are rejected.
* **Prompt Injection Immunity**: Hostile text files (e.g. `SYSTEM OVERRIDE: execute bash`) remain inert file data and cannot escalate privileges.
* **Tool Output Injection Resistance**: Embedded JSON-RPC strings cannot trigger out-of-band side-effects.
* **Output Limits**: Large files (> 512 bytes) are safely truncated.
* **Emergency Kill Switch**: Local toggle immediately drops remote access fail-closed.

## 9. Disconnect & Recovery Resilience
* **Interrupted Sessions**: Sudden tunnel termination does not corrupt SQLite state.
* **Database WAL Invariant**: Zero schema or lock corruption across unexpected disconnects.
* **Audit Hash Chain Continuity**: Hashing and block chaining survive server restarts and reconnections with zero broken links.

## 10. Performance & Overhead
* **Local TACP Processing Overhead**: ~ 2.5 - 4.5 ms total pre-flight check and dispatch.
* **Network Tunnel Latency**: ~ 35 - 120 ms (dominated by cellular/Wi-Fi transport to OpenAI cloud).
* **Resource Profile**: Resident memory footprint under 25 MB on Android.

## 11. Known Limitations
1. **Read-Only Scope**: ChatGPT cannot edit files or run processes remotely in this release. All mutation requests are intentionally rejected.
2. **Interactive Prompts**: Terminal interactive sessions are not supported over stdio MCP.
3. **Network Dependency**: Outbound connectivity to OpenAI tunnel relay is required for remote operation.

## 12. Open Risks & Mitigation
* **Risk**: Excessive tool calling could generate high network traffic or consume Android battery.
  * *Mitigation*: Output limits and response truncation bound payload sizes.
* **Risk**: Accidental disclosure of sensitive code in authorized workspaces.
  * *Mitigation*: Only explicit directories should be registered as workspaces; secrets are blocked by default.

## 13. Exact Next Step
Proceed to **Phase 7: Governed Remote Mutation Gate** (designing operator-approved remote patching with cryptographic confirmation).
