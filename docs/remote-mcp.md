# TACP Remote MCP Setup & Client Integration Guide

This guide details how to connect any AI agent or development environment to your Android device via **TACP (Termux AI Control Plane)** using standard Model Context Protocol (MCP) Streamable HTTP or Stdio transports.

---

## 1. Quickstart: Enabling Remote Access on Android

On your Android device inside Termux:

### Step 1: Create an Authentication Token
```bash
tacp auth create --name "My Desktop Agent" --scopes "tacp.read,tacp.files.read,tacp.files.write"
```
Output:
```
============================================================
 TACP Authentication Token Created
============================================================
Token ID     : tok_7a1b2c3d4e5f
Name         : My Desktop Agent
Scopes       : tacp.read, tacp.files.read, tacp.files.write
Principal ID : remote_my_desktop_agent
Created At   : 2026-09-24T18:00:00+00:00

------------------------------------------------------------
BEARER TOKEN (Save this now - it will never be shown again):
  <TACP_AUTH_TOKEN>
------------------------------------------------------------
```

### Step 2: Enable Remote MCP Connectivity

Choose the provider suitable for your network setup:

#### Option A: Cloudflare Quick Tunnel (Easiest - Works across cellular NAT)
```bash
tacp remote enable --provider cloudflare
```
Output:
```
============================================================
 TACP Remote MCP Connectivity Activated
============================================================
Provider     : cloudflare
Device ID    : dev_6c478a2e19b0
Device Name  : Android-Galaxy-S24
MCP Endpoint : https://unique-subdomain.trycloudflare.com/mcp
```

#### Option B: Direct LAN or Tailscale (Fastest - Local Network / Mesh VPN)
```bash
# If using Tailscale or Local LAN IP
tacp remote enable --provider direct --custom-domain 100.85.12.34 --port 8765
```
Endpoint: `http://100.85.12.34:8765/mcp`

#### Option C: Self-Hosted Relay Gateway (Enterprise / High Reliability)
```bash
tacp remote enable --provider relay --gateway-url https://gateway.yourdomain.com
```

---

## 2. Client Configuration Guides

### 2.1 Claude Desktop

Add TACP to your `claude_desktop_config.json`:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

#### Streamable HTTP (Remote Connection)
```json
{
  "mcpServers": {
    "tacp-phone": {
      "url": "https://unique-subdomain.trycloudflare.com/mcp",
      "headers": {
        "Authorization": "Bearer <TACP_AUTH_TOKEN>"
      }
    }
  }
}
```

#### Stdio over SSH (Local / Cable Connection)
```json
{
  "mcpServers": {
    "tacp-phone-ssh": {
      "command": "ssh",
      "args": [
        "-p", "8022",
        "u0_a316@phone-ip.local",
        "/data/data/com.termux/files/usr/bin/tacp",
        "serve-stdio"
      ]
    }
  }
}
```

---

### 2.2 Cursor IDE

Open Cursor Settings -> **Features** -> **MCP Servers** -> **Add New MCP Server**, or add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "android-tacp": {
      "url": "https://unique-subdomain.trycloudflare.com/mcp",
      "headers": {
        "Authorization": "Bearer <TACP_AUTH_TOKEN>"
      }
    }
  }
}
```

---

### 2.3 Visual Studio Code

Using the official Model Context Protocol extension or Claude Code in VS Code:

In `.vscode/settings.json`:
```json
{
  "mcp.servers": {
    "tacp": {
      "type": "http",
      "url": "https://unique-subdomain.trycloudflare.com/mcp",
      "headers": {
        "Authorization": "Bearer <TACP_AUTH_TOKEN>"
      }
    }
  }
}
```

---

### 2.4 ChatGPT (Custom GPT / Remote MCP Action)

When configuring a Custom GPT or Developer MCP Connector in OpenAI:

1. **Server URL**: `https://unique-subdomain.trycloudflare.com/mcp`
2. **Authentication**: `Bearer Token`
3. **Token**: `<TACP_AUTH_TOKEN>`

Alternatively, if connecting through the dedicated OpenAI tunnel integration:
```bash
python -m tacp.vendors.openai.adapter --port 8765
```

---

### 2.5 Raw HTTP / cURL Verification

Test connection and list registered tools from your workstation terminal:

```bash
# 1. Health check
curl -s https://unique-subdomain.trycloudflare.com/health

# 2. Handshake (initialize)
curl -s -X POST https://unique-subdomain.trycloudflare.com/mcp \
  -H "Authorization: Bearer <TACP_AUTH_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2026-07-28"}}'

# 3. List available tools
curl -s -X POST https://unique-subdomain.trycloudflare.com/mcp \
  -H "Authorization: Bearer <TACP_AUTH_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}'

# 4. Invoke system.inspect
curl -s -X POST https://unique-subdomain.trycloudflare.com/mcp \
  -H "Authorization: Bearer <TACP_AUTH_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "system.inspect", "arguments": {}}}'
```

---

## 3. Remote CLI Reference

| Command | Description |
|---|---|
| `tacp remote status` | Display active provider, device ID, public endpoint, and state. |
| `tacp remote enable [--provider P]` | Activate remote access (`cloudflare`, `relay`, `direct`). |
| `tacp remote disable` | Terminate all active tunnels and background HTTP servers. |
| `tacp remote url` | Print current public MCP endpoint URL. |
| `tacp remote pair [--ttl 10]` | Generate short-lived pairing code (`XXXX-XXXX`) for device verification. |
| `tacp auth create --name <N>` | Issue a new Bearer authentication token. |
| `tacp auth list [--all]` | List all active or revoked authentication tokens. |
| `tacp auth revoke <token_id>` | Immediately invalidate a token. |
