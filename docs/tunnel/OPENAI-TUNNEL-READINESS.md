# OpenAI Tunnel Readiness & Remote Access Architecture

- **Document Version**: 1.0.0
- **Target**: TACP Remote Agent Integration
- **Classification**: Engineering Architecture & Threat Model

---

## 1. Executive Architecture Overview

TACP natively operates as a local process inside Termux communicating via standard I/O (stdio). To enable remote AI models (such as GPT-4o or OpenAI-compatible endpoints) or external agent orchestrators to interact with TACP, a secure network ingress tunnel and protocol translation bridge are required.

```
┌─────────────────────────┐
│ Remote AI Agent Engine  │
│ (OpenAI Tools Schema)   │
└────────────┬────────────┘
             │ HTTPS / WSS / SSH
             ▼
┌─────────────────────────┐
│     Ingress Tunnel      │  (Tailscale / Cloudflare / SSH)
│ (TLS Termination, Auth) │
└────────────┬────────────┘
             │ Loopback (127.0.0.1) or Stdio
             ▼
┌─────────────────────────┐
│ OpenAI -> MCP Adapter   │  (Protocol Translator)
└────────────┬────────────┘
             │ Stdio / JSON-RPC 2.0
             ▼
┌─────────────────────────┐
│        TACP 0.1         │
│  - Policy Engine        │  (Strict Read-Only Enforcement)
│  - Tamper-Evident Audit │  (Cryptographic Event Logging)
│  - Providers            │  (Filesystem, Process, System)
└─────────────────────────┘
```

---

## 2. Transport Ingress Options & Security Analysis

| Transport | Architecture | Auth & Encryption | Exposure Surface | Suitability for Termux |
|---|---|---|---|---|
| **1. Tailscale Funnel / Serve** | WireGuard overlay mesh to node or authenticated Tailnet endpoint | WireGuard end-to-end encryption; node identity; SSO auth | Private mesh (Funnel exposes public DNS with TLS) | **RECOMMENDED**. Zero open router ports; minimal battery overhead; authenticated per node. |
| **2. Cloudflare Tunnel (`cloudflared`)** | Outbound reverse tunnel to Cloudflare Edge | TLS at edge + TLS to daemon; Cloudflare Access Zero Trust policies | Public hostname protected by Cloudflare Access MFA / Service Tokens | **STRONG ALTERNATIVE**. Excellent for public webhook/agent callbacks without public IP. |
| **3. Stdio over SSH (`sshd`)** | Direct SSH command invocation: `ssh user@host "tacp serve"` | SSH keypair (ED25519); robust transport encryption | Port exposed (or combined with Tailscale) | **SIMPLEST & SAFEST**. Bypasses HTTP entirely; no web attack surface; native stdio forwarding. |
| **4. Reverse WebSocket** | Termux client initiates outbound WS connection to cloud broker | WSS (TLS 1.3); custom bearer token / HMAC handshake | Broker handles routing; mobile device has 0 inbound listening sockets | Good for hostile NATs, but requires running a cloud relay. |

---

## 3. Protocol Mapping: OpenAI Tools <-> MCP

OpenAI Function Calling format and MCP tool invocation format map naturally:

### 3.1 Mapping Schema
```
OpenAI Tool Call:
{
  "id": "call_abc123",
  "type": "function",
  "function": {
    "name": "fs_read",
    "arguments": "{\"workspace_id\":\"ws1\",\"subpath\":\"main.py\"}"
  }
}
                    │
                    ▼  Adapter Translation
MCP JSON-RPC Request:
{
  "jsonrpc": "2.0",
  "id": "call_abc123",
  "method": "tools/call",
  "params": {
    "name": "fs.read",
    "arguments": {
      "workspace_id": "ws1",
      "subpath": "main.py"
    },
    "_meta": {
      "openai_call_id": "call_abc123"
    }
  }
}
```

### 3.2 Result Translation
```
MCP JSON-RPC Response:
{
  "jsonrpc": "2.0",
  "id": "call_abc123",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"path\":\"main.py\",\"content\":\"print('hello')\"}"
      }
    ],
    "isError": false,
    "resultType": "complete"
  }
}
                    │
                    ▼  Adapter Translation
OpenAI Tool Result Message:
{
  "role": "tool",
  "tool_call_id": "call_abc123",
  "content": "{\"path\":\"main.py\",\"content\":\"print('hello')\"}"
}
```

---

## 4. Latency Budget Analysis

In a mobile Termux environment, latency is dominated by wireless network hops. The budget must be modeled rigorously:

| Segment | Estimated Latency | Optimization / Mitigation |
|---|---|---|
| **Radio / Carrier Network (4G/5G/Wi-Fi)** | 20 ms – 150 ms | Keep TCP/TLS sessions persistent (HTTP/2 or SSH mux). |
| **Tunnel Overlay (Tailscale DERP / Cloudflare Edge)** | 10 ms – 60 ms | Direct WireGuard p2p connection minimizes DERP relaying. |
| **Adapter Protocol Translation** | < 1 ms | Pure in-memory JSON transform in Python/Node. |
| **TACP Stdio Dispatch & Policy Check** | < 2 ms | In-memory policy rules; zero network dependencies. |
| **Termux Filesystem / Proc Read** | 0.5 ms – 8 ms | Flash storage I/O and kernel procfs virtual reads. |
| **Total Round-Trip (Excluding LLM Inference)** | **33.5 ms – 221 ms** | Fully acceptable for interactive agent workflows. |

---

## 5. Remote Authentication & Verification Standards

When exposing TACP remotely (even via VPN or tunnel), authentication must be defense-in-depth:
1. **Transport Layer Auth**: Tailscale node key or SSH ED25519 keypair.
2. **Application Layer Auth**:
   - HTTP Bearer Token (`Authorization: Bearer <entropy-64-token>`) with timing-safe comparison.
   - Or HMAC-SHA256 request signing (`X-TACP-Signature: t=timestamp,v1=signature`) preventing replay attacks.
3. **Identity Binding in TACP**:
   - The remote principal is passed to TACP RequestContext (e.g. `Principal(id="remote-gpt4o", role="agent")`).
   - Every remote request is immutably recorded in the tamper-evident SQLite audit log with remote principal metadata.

---

## 6. Threat Model for Remote Access (Read-Only Exposure)

Even though TACP 0.1 is strictly read-only and eliminates mutation/execution hazards, remote exposure introduces distinct risks:

| Threat | Impact | TACP Defense |
|---|---|---|
| **Unauthorized Information Disclosure** | Remote attacker reads private files / source code | Workspace jailing strictly restricts reads to authorized directory roots. |
| **Secret Exposure** | Remote attacker reads API keys or `.env` files | Secret redaction filters strip tokens, private keys, and credential blocks. |
| **Denial of Service / Battery Exhaustion** | Flooding requests drains mobile battery | Bounded response limits, concurrency limits, and OS socket timeouts. |
| **Audit Log Tampering** | Attacker attempts to erase access evidence | Cryptographic hash chaining (`sha256(prev_hash + entry)`) reveals any deletion or modification. |
| **ReDoS / Algorithmic Complexity** | Malicious regex searches consume CPU | Timeout on regex evaluation, safe fallback substring matching. |

---

## 7. Prototype Simulation Harness

A complete automated test harness simulating the end-to-end pipeline:
`Simulated OpenAI Tool Call -> Adapter -> TACP MCP Server -> Response Translation`
is implemented and verified in `tests/integration/test_openai_tunnel.py` without requiring external networks or cloud credentials.
