# TACP — Termux AI Control Plane

> **A secure, agent-agnostic universal remote Model Context Protocol (MCP) server running natively on Android via Termux.**

[![MCP Version](https://img.shields.io/badge/MCP-2026--07--28%20Streamable%20HTTP-blueviolet)](#mcp-protocol-conformance)
[![Tests Passing](https://img.shields.io/badge/tests-817%20passing-success)](#verification--test-metrics)
[![Release](https://img.shields.io/badge/release-v0.4.0--rc.1-orange)](CHANGELOG.md)
[![License](https://img.shields.io/badge/license-MIT-informational)](LICENSE)

---

## 1. Overview & Mental Model

**"TACP is a secure, standard-compliant Model Context Protocol server that happens to run on Android."**

TACP transforms your Android device into a powerful, policy-governed control plane accessible by any AI agent—including **Claude Desktop, Cursor IDE, VS Code, ChatGPT, Gemini, autonomous coding agents, and custom Python/TypeScript MCP SDK clients**.

TACP operates on an uncompromising constitutional principle:
> ***"AI MAY BE AUTONOMOUS, BUT AI MUST NEVER BE SOVEREIGN."***

Instead of giving AI models unrestricted shell access or raw filesystem privileges, TACP enforces an authoritative governance barrier:
- **Dual Transports**: Streamable HTTP (`POST /mcp`, `GET /mcp` with SSE streaming, `Mcp-Session-Id`) and local Stdio (`tacp serve-stdio`).
- **Cryptographic Authentication**: Bearer tokens (`tacp_sec_<hex>`) hashed with SHA-256 into SQLite (never stored in plaintext).
- **Fine-Grained Scopes**: `tacp.read`, `tacp.files.read`, `tacp.files.write`, `tacp.system.read`, `tacp.process.read`, `tacp.execute`, and `tacp.admin`.
- **Filesystem Jailing**: Access confined exclusively to explicitly registered workspaces (`termux-home`, `phone-storage`). Absolute defense against directory traversal (`..`), symlink escapes, and credential file theft.
- **Governed Zero-Shell Execution**: Controlled execution with `shell=False` (no `/bin/sh` or `bash -c`), process session isolation (`setsid`), watchdog timers, and interactive human approval.
- **Tamper-Evident Audit Trail**: Every access, policy decision, mutation, and command is recorded in a cryptographically chained SHA-256 hash log (`tacp audit verify`).
- **Remote NAT-Traversal Options**: Built-in support for Cloudflare Quick Tunnels, Direct LAN/Tailscale mesh, and self-hosted outbound relay gateway (`tacp gateway`).

---

## 2. Architecture & Subsystems

```
+-----------------------------------------------------------------------------------+
|                            Remote / Local AI Clients                              |
|   Claude Desktop  |  Cursor IDE  |  VS Code  |  ChatGPT  |  Custom Agents/SDKs    |
+-----------------------------------------------------------------------------------+
                                         |
                       [Streamable HTTP / Stdio Transports]
                                         |
+-----------------------------------------------------------------------------------+
|                        TACP Access Layer (MCP Transports)                         |
|   - StreamableMcpServer (/mcp, /health, /ready, /status)                          |
|   - StdioRunner (JSON-RPC 2.0 over standard I/O)                                  |
|   - Session Tracking (Mcp-Session-Id), CORS, SSE Streaming                        |
+-----------------------------------------------------------------------------------+
                                         |
+-----------------------------------------------------------------------------------+
|                      TACP Control Layer (Governance & Auth)                       |
|   - TokenService (SHA-256 Bearer Token Verification & Scope Hierarchy)            |
|   - PairingService (Ephemeral XXXX-XXXX Device Pairing Exchange)                  |
|   - PolicyEngine (Default-Deny Invariants, Workspace Jailing, Risk Classification) |
|   - ApprovalEngine & LeaseEngine (Interactive Human Approval & Capability Leases) |
|   - AuditService (Cryptographic SHA-256 Tamper-Evident Event Chaining)            |
+-----------------------------------------------------------------------------------+
                                         |
+-----------------------------------------------------------------------------------+
|                           TACP Core Services Layer                                |
|   - WorkspaceService (Multi-root Registry, Containment, Normalization)            |
|   - FilesystemService (Jailed Read, Search, Stat, Canonical Boundaries)          |
|   - PatchService (Atomic Unified Diff Application, Rollback, Staging)            |
|   - ExecutionService (Governed Process Execution, Zero-Shell, Watchdogs)          |
|   - SystemService & CapabilityService (OS Diagnostics, Battery, Telemetry)        |
+-----------------------------------------------------------------------------------+
```

Detailed technical documentation:
- [System Architecture](docs/architecture.md)
- [Remote MCP & Client Guide](docs/remote-mcp.md)
- [Security & Governance](docs/security.md)
- [Self-Hosting Guide](docs/self-hosting.md)
- [Client Integration Examples](docs/client-examples.md)

---

## 3. Quick Start

### 3.1 Setup on Android (Termux)

```bash
# 1. Clone repository
git clone https://github.com/The-habib/tacp.git
cd tacp

# 2. Run diagnostics
./doctor

# 3. Create an authentication token
tacp auth create --name "My Desktop Agent" --scopes "tacp.read,tacp.files.read,tacp.files.write"
# Output gives: tacp_sec_<hex_token>

# 4. Enable remote access via Cloudflare Quick Tunnel (or direct LAN)
tacp remote enable --provider cloudflare
# Output gives: https://<subdomain>.trycloudflare.com/mcp
```

### 3.2 Connecting Clients

#### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "tacp-phone": {
      "url": "https://<subdomain>.trycloudflare.com/mcp",
      "headers": {
        "Authorization": "Bearer tacp_sec_<YOUR_TOKEN>"
      }
    }
  }
}
```

#### Cursor IDE (`.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "tacp-phone": {
      "url": "https://<subdomain>.trycloudflare.com/mcp",
      "headers": {
        "Authorization": "Bearer tacp_sec_<YOUR_TOKEN>"
      }
    }
  }
}
```

#### Standalone Verification Script (Zero Client Dependencies)
Verify your running server without needing any commercial AI account:
```bash
python scripts/test_mcp_http.py --url http://127.0.0.1:8765 --token tacp_sec_<YOUR_TOKEN>
```

---

## 4. CLI Command Reference

### Server & Transports
- `tacp serve-http [--host 0.0.0.0] [--port 8765] [--auth]`: Launch Streamable HTTP MCP server.
- `tacp serve-stdio`: Launch standard I/O MCP transport for local agents / SSH pipes.
- `tacp gateway [--port 9090]`: Run standalone self-hosted Remote MCP Gateway.

### Authentication & Identity
- `tacp auth create --name <NAME> [--scopes <SCOPES>] [--expires <DAYS>]`: Issue cryptographically secure Bearer token.
- `tacp auth list [--all]`: List active or revoked tokens.
- `tacp auth revoke <TOKEN_ID>`: Invalidate a token immediately.
- `tacp remote pair [--ttl 10]`: Generate short-lived pairing code (`XXXX-XXXX`) for device verification.

### Remote Tunneling
- `tacp remote status`: Inspect active tunnel provider, device ID, public endpoint, and status.
- `tacp remote enable [--provider cloudflare|relay|direct]`: Activate remote MCP endpoint.
- `tacp remote disable`: Terminate active tunnels and background servers.
- `tacp remote url`: Print active public MCP endpoint URL.

### Workspaces & Security
- `tacp workspace list`: Show registered workspaces (`termux-home`, `phone-storage`).
- `tacp workspace add <PATH> --name <NAME>`: Register a new workspace directory.
- `tacp workspace remove <NAME|ID>`: Unregister a workspace.
- `tacp audit recent [--limit 20]`: View recent audit log records.
- `tacp audit verify`: Cryptographically verify tamper-evident SHA-256 hash chain.
- `tacp audit reanchor`: Recompute and repair hash pointers across all historical records.
- `tacp execution emergency-stop`: Kill all running child processes immediately.

---

## 5. Verification & Test Suite

Run canonical verification:
```bash
pytest
```
All 817 automated tests validate:
- Multi-lane admission control (64 FAST_READ, 8 FILESYSTEM, 4 PROCESS, 4 COMPANION, 2 MEDIA, 2 MUTATION).
- SingleFlight cache stampede coalescing and stratified negative caching.
- Companion transport persistent keep-alive and fail-fast circuit breaker.
- Streamable HTTP protocol conformance (GET/POST `/mcp`, SSE streaming, `Mcp-Session-Id`, 401 Unauthorized).
- Bearer token hashing, scope hierarchies, expiration, and revocation.
- Ephemeral pairing code exchange (`XXXX-XXXX`).
- Remote manager lifecycle and multi-provider tunnels.
- Governed execution, process isolation, and watchdog timeouts.
- Filesystem jailing, path traversal rejection, and secret redaction.
- Cryptographic SHA-256 audit chaining and pinpoint verification.

---

## 6. License

MIT License. Copyright (c) 2026 The Habib / TACP Team.
