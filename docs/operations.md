# TACP Production Operations Manual

This document provides day-to-day operational procedures for administrators and developers operating TACP as a remote MCP server on Android/Termux.

---

## 1. Quick Startup & Service Management

### Start Streamable MCP Server Locally
```bash
tacp serve-http --host 127.0.0.1 --port 8765
```

### Start Remote Tunnel Daemon (Cloudflare Quick Tunnel)
```bash
tacp remote enable --provider cloudflare --port 8765
```

### Check Tunnel & Service Status
```bash
tacp remote status
tacp status
```

### Disable Remote Tunnel
```bash
tacp remote disable
```

---

## 2. Token Lifecycle Management

### Create Token
Create an agent-specific Bearer token with least-privilege scopes:
```bash
# Read-only token for monitoring
tacp auth create --name "Monitoring Agent" --scopes tacp.read,tacp.system.read

# Full workspace token for development pair-programmer
tacp auth create --name "Dev Agent" --scopes tacp.read,tacp.files.read,tacp.files.write,tacp.system.read,tacp.process.read
```

### List Active Tokens
```bash
tacp auth list
```

### Revoke Token
```bash
tacp auth revoke <token_id>
```

---

## 3. End-to-End Diagnostics

To verify the complete remote chain (Local MCP Server → SQLite → Cloudflare Edge → Internet):
```bash
tacp remote test
```

To run the full environmental and integrity check:
```bash
./doctor
tacp audit verify
```

---

## 4. Connection Bundle Management

Export the connection bundle and universal connection prompt anytime:
```bash
tacp connection export
```
Files generated:
- `~/.tacp/tacp-connection.json`: Machine-readable client configuration (Claude, Cursor, VS Code, OpenAI).
- `~/.tacp/tacp-agent-connect-prompt.txt`: Copy-paste prompt ready for any AI model.

---

## 5. Security & Isolation

- **Jailing**: All file operations are strictly restricted to registered workspaces (`termux-home` and `phone-storage`). Directory traversal attempts (`../../`) are blocked and audited.
- **Execution**: Command execution bypasses shell interpreters (`shell=False`) to prevent injection.
- **Audit**: Every action produces an append-only, SHA-256 hash-chained event stored in SQLite WAL mode.
