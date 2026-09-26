# TACP Troubleshooting & Operations Diagnostic Guide

This guide covers common diagnostic scenarios, failure modes, root causes, and resolutions for running the Termux AI Control Plane (TACP) as a universal remote MCP server.

---

## 1. Android Background Execution & Sleep Prevention

### Symptom:
TACP server stops responding after 1-5 minutes when phone screen turns off.

### Root Cause:
Android aggressive battery management (Doze mode) suspends Termux background processes and drops network sockets.

### Resolution:
1. **Acquire Termux Wake Lock**:
   ```bash
   termux-wake-lock
   ```
2. **Disable Battery Optimization**:
   - Go to Android Settings → Apps → Termux → Battery → Select **"Unrestricted"**.
3. **Keep Termux in Recent Apps**:
   - Lock Termux in your device's recent app switcher.

---

## 2. Cloudflare Tunnel Connectivity Issues

### Symptom:
`cloudflared` hangs or fails with:
`failed to connect to an edge ... dial tcp: lookup ... error 1033`

### Root Cause:
Android mobile carriers (e.g. Jio, Airtel, T-Mobile, Verizon) frequently fail to assign valid public IPv6 routes to local Termux sockets. Default `cloudflared` attempts dual-stack IPv6 to Cloudflare Edge (`auto`), dropping connections.

### Resolution:
TACP's `CloudflareTunnelProvider` automatically forces IPv4 with `--edge-ip-version 4`.
To test manually:
```bash
cloudflared tunnel --url http://127.0.0.1:8765 --edge-ip-version 4 --no-autoupdate
```

---

## 3. Remote Verification Failure (401 Unauthorized)

### Symptom:
Client receives `HTTP 401: Missing or invalid Authorization header`.

### Root Cause:
Bearer token missing, incorrect format, or revoked in SQLite database.

### Resolution:
1. Ensure the header matches exact format:
   ```http
   Authorization: Bearer tacp_sec_<64_hex_chars>
   ```
2. Check token validity in TACP CLI:
   ```bash
   tacp auth list
   ```
3. Issue a new universal token if necessary:
   ```bash
   tacp auth create --name "Universal Agent" --scopes tacp.read,tacp.files.read,tacp.files.write,tacp.system.read,tacp.process.read
   ```

---

## 4. MCP Streamable HTTP Session ID Mismatch

### Symptom:
Sequential POST requests return `404 Session Not Found` or fail notifications.

### Root Cause:
The MCP Streamable HTTP transport specification requires clients to retain and reuse the `Mcp-Session-Id` header returned by the server on initialization.

### Resolution:
Ensure your client or custom script captures `Mcp-Session-Id` from the initial handshake response and sends it on subsequent requests:
```python
session_id = resp.headers.get("Mcp-Session-Id")
headers["Mcp-Session-Id"] = session_id
```

---

## 5. Storage Permission Denied (`/storage/emulated/0`)

### Symptom:
Filesystem tools fail with `PermissionDenied` when accessing `phone-storage`.

### Root Cause:
Termux has not been granted Android storage access permission.

### Resolution:
1. Request Android storage permission:
   ```bash
   termux-setup-storage
   ```
2. Approve the prompt on your Android screen.
3. Verify workspace registration:
   ```bash
   tacp workspace list
   ```

---

## 6. Audit Chain Verification Failure

### Symptom:
`tacp audit verify` returns `[FAIL] Tampering detected`.

### Root Cause:
SQLite database was directly modified with `sqlite3` without using TACP's cryptographic hash chain.

### Resolution:
TACP's audit log is append-only and cryptographically bound via SHA-256 genesis-anchored hashes. If tampered, inspect the recent log entries:
```bash
tacp audit recent --limit 50 --json
```

---

## 7. Diagnostic Checklist

Run the built-in diagnostic test:
```bash
tacp doctor
tacp remote test
```
All checks must display `[PASS]`.
