# TACP Local MCP Baseline Specification

## 1. Executive Summary
TACP (Termux AI Control Plane) provides a standards-compliant Model Context Protocol (MCP) server running natively on Android via Termux `aarch64`. This document defines the verified local MCP transport baseline that serves as the foundation for the OpenAI Secure MCP Tunnel.

## 2. Transport Architecture
* **Primary Transport**: Standard Input / Standard Output (`stdio`).
* **Format**: JSON-RPC 2.0 delimited by newline characters (`\n`).
* **Diagnostic Channel**: Standard Error (`stderr`) strictly reserved for all logging, diagnostic messages, and doctor outputs.
* **Stdout Invariant**: Zero banner pollution, zero debug noise, zero non-JSON-RPC text emitted to stdout.

## 3. Protocol Specification & Capabilities
* **Negotiated Protocol Version**: `2026-07-28`.
* **Fallback Protocol Version**: `2024-11-05`.
* **Server Identification**:
  * Name: `tacp`
  * Version: `0.4.0-rc.1` / `0.5.1-rc.1`
  * Description: `Termux AI Control Plane (TACP) local MCP server providing safe inspection and policy-controlled workspace operations.`
* **Core Supported Methods**:
  * `initialize`: Protocol negotiation, client metadata registration, server capability declaration.
  * `ping`: Liveness check returning an empty object `{}`.
  * `tools/list`: Dynamic capability listing filtered by active trust profile and flags.
  * `tools/call`: Controlled capability invocation governed by `PolicyEngine`.

## 4. Verification Evidence
A raw stdio test confirmed that feeding newline-delimited JSON-RPC packets into `tacp serve` yields syntactically pure JSON-RPC responses:
```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2026-07-28","clientInfo":{"name":"test"},"capabilities":{}}}
{"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2026-07-28", "capabilities": {"tools": {"listChanged": true}}, "serverInfo": {"name": "tacp", "version": "0.4.0-rc.1", "description": "Termux AI Control Plane (TACP) local MCP server providing safe inspection and policy-controlled workspace operations."}}}
```

Diagnostic logs were successfully diverted to `stderr` without interfering with protocol parsers:
```
[INFO] Starting TACP stdio MCP server (PID: 14728)
[INFO] Serving workspaces: ['/data/data/com.termux/files/home/projects/tacp']
```

## 5. Security Invariant
The local MCP stdio server operates under principle of least privilege. When invoked via the tunnel adapter, all requests default to the `REMOTE_AI` principal and the `REMOTE_READ_ONLY` trust profile.
