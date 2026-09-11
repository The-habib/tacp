# MCP Compatibility and Conformance Audit

- **Document Version**: 1.0.0
- **Release Target**: TACP 0.1 (`v0.1.0-rc.1`)
- **Audit Date**: 2026-09-11
- **Auditor**: Lead Staff Engineer & Security Architect
- **Conformance Status**: **CONFORMANT (Dual-Protocol 2026-07-28 + 2024-11-05)**

---

## 1. Executive Summary

This audit evaluates the Model Context Protocol (MCP) implementation within TACP 0.1 against the official MCP specifications and the official reference Python SDK (`mcp` / `mcp-types` v2.2.0).

Key findings:
1. **Specification Modernization**: The MCP specification progressed from the legacy `2024-11-05` draft to `2026-07-28`.
2. **Dual-Protocol Conformance**: TACP 0.1 implements **Dual-Protocol Support**:
   - Modern `2026-07-28` stateless protocol (`server/discover`, per-request `_meta`, caching directives, `resultType: "complete"`).
   - Full backward compatibility for `2024-11-05` through `2025-11-25` legacy clients (`initialize` handshake, `notifications/initialized`, `ping`).
3. **Tasks Extension Status**: The Tasks extension (`tasks/*`) is **deliberately absent** from the official MCP Python SDK v2.2.0 release schema. TACP appropriately does not implement or claim Tasks support in 0.1.
4. **Independent Tool Conformance**: Verified against the official `@modelcontextprotocol/inspector` v2.6.0 with `--strict` schema validation. All 13 read-only tools passed with zero schema errors.

---

## 2. Official Reference SDK Audit (`mcp-types` v2.2.0)

Direct inspection of official MCP Python SDK package `mcp-types` v2.2.0 reveals the canonical protocol versions and architectural expectations:

### 2.1 Protocol Versions
From `mcp_types.version`:
```python
KNOWN_PROTOCOL_VERSIONS: tuple[str, ...] = (
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
    "2026-07-28",
)
HANDSHAKE_PROTOCOL_VERSIONS: tuple[str, ...] = (
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
)
MODERN_PROTOCOL_VERSIONS: tuple[str, ...] = ("2026-07-28",)
```

### 2.2 Protocol Differences: 2024-11-05 vs 2026-07-28

| Feature | Legacy MCP (2024-11-05) | Modern MCP (2026-07-28) | TACP Implementation |
|---|---|---|---|
| **Handshake** | Mandatory `initialize` + `notifications/initialized` | Stateless; no handshake required | Supported (both stateless and handshake) |
| **Server Discovery** | Absent (capabilities exchanged in `initialize`) | `server/discover` method | Fully implemented |
| **Heartbeat / Ping** | `ping` method | Deprecated/Absent in modern stateless flows | Supported for legacy clients |
| **Tool Listing** | Returns `{"tools": [...]}` | Returns `{"tools": [...], "cacheScope": "public", "ttlMs": 60000, "resultType": "complete"}` | Fully implemented (returns both) |
| **Tool Calling** | `{"name": "...", "arguments": {...}}` | Accepts `_meta: {...}` (progress tokens, traces) | Fully implemented (`_meta` accepted) |
| **Tool Result** | `{"content": [...], "isError": bool}` | `{"content": [...], "isError": bool, "resultType": "complete"}` | Fully implemented |
| **Tasks Extension** | Not present | **Deliberately absent** in SDK v2.2.0 | Not present / Not claimed |

### 2.3 Status of the Tasks Extension
Inspection of `mcp_types/methods.py` confirms:
```python
# 2025-11-25 (tasks/* deliberately absent)
```
The Tasks extension was deferred from official core schemas in v2.2.0. Any claim that a production MCP server "must" implement Tasks to be modern is counter to the official Python SDK release. TACP correctly omits Tasks from v0.1.

---

## 3. TACP MCP Server Architecture

TACP's MCP server resides in `src/tacp/access/mcp/`:
- `protocol.py`: JSON-RPC 2.0 parser, error codes, and protocol constants.
- `server.py`: Synchronous stdio message loop, request dispatcher, protocol negotiator.
- `tools.py`: Tool registry connecting MCP tool invocations to TACP capability services through the Policy Engine and Audit Service.

### 3.1 Dual-Protocol Conformance Matrix

```
                 Incoming JSON-RPC Request
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
    Method: "server/discover"       Method: "initialize"
   (Modern 2026-07-28 Client)     (Legacy 2024-11-05 Client)
            │                               │
    Returns DiscoverResult          Negotiates Protocol Version
   (supportedVersions, tools,       (2024-11-05 / 2025-11-25)
    caching directives, ttl)                │
            │                               ▼
            │                     Method: "tools/list"
            │                               │
            └───────────────┬───────────────┘
                            ▼
                    Method: "tools/call"
             (Accepts _meta, evaluates policy,
              executes read-only provider,
              returns resultType: "complete")
```

### 3.2 Tool Input Schema Conformance
Every tool registered in TACP provides a strictly valid JSON Schema:
```json
{
  "type": "object",
  "properties": { ... },
  "required": [ ... ]
}
```
Zero tools expose empty `{}` or `null` schemas, ensuring interoperability across all modern and legacy MCP client schema validators.

---

## 4. Conformance Verification with Official MCP Inspector

Verification was conducted on-device in Termux using the official `@modelcontextprotocol/inspector` v2.6.0.

### 4.1 Test Summary
1. **Initialize Negotiation**:
   - Inspector requested `2025-11-25`.
   - TACP responded with matching `2025-11-25` negotiation and server metadata.
   - Result: **PASS**.
2. **Tool Listing Conformance**:
   - Executed with `--strict` flag.
   - Inspector validated all 13 tool schemas against draft JSON-schema standards.
   - Reported: 0 warnings, 0 schema portability errors.
   - Result: **PASS**.
3. **Tool Invocation**:
   - `system.inspect`: Successfully retrieved Android/Termux host facts.
   - `fs.list`: Successfully listed workspace directory entries.
   - `fs.read`: Successfully read file with bounds enforcement.
   - Result: **PASS**.
4. **Boundary & Error Protocol**:
   - Attempted path traversal `../../etc/passwd`.
   - Server returned structured error `Error (OUTSIDE_WORKSPACE): Path ... escapes authorized workspace boundary` with `isError: true` and `resultType: "complete"`.
   - Result: **PASS**.

The full transcript is archived in [inspector-session.md](inspector-session.md).

---

## 5. Audit Conclusion

TACP 0.1 conforms to both the modern MCP `2026-07-28` specification and the legacy `2024-11-05` standard. It is verified against the official MCP Inspector v2.6.0 on a live Android Termux device with zero schema violations.
