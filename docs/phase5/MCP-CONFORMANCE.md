# TACP Phase 5: MCP Protocol Conformance and Security Audit
**Document ID:** `TACP-MCP-CONF-001`  
**Classification:** Protocol Adapter Specification  
**Release Target:** v0.4.0-rc.1 Hardening / Phase 5  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Role of the Model Context Protocol (MCP) in TACP

The MCP interface is an **untrusted adapter**, never a security boundary or authority conferring mechanism.
Every MCP tool invocation (`tools/call`) translates parameters directly into an internal `RequestContext` with a `Principal(principal_type=AGENT, trust_tier=RESTRICTED)` and routes through the standard 16-stage governed execution pipeline.

There is **zero** MCP-specific execution bypass.

---

## 2. Formal MCP Feature Conformance Matrix

Evaluated against the Model Context Protocol Specification (2024-11-05 / 2025 / 2026 revisions):

| Protocol Feature | Implementation Status | Technical Mechanism / Endpoint | Compliance Level |
| :--- | :--- | :--- | :--- |
| **JSON-RPC 2.0 Framing** | SUPPORTED | Line-delimited newline JSON over `sys.stdin`/`sys.stdout` | Full Conformance |
| **Protocol Handshake (`initialize`)** | SUPPORTED | Protocol version negotiation, returns server capabilities | Full Conformance |
| **Ping (`ping`)** | SUPPORTED | Returns `{}` acknowledgment | Full Conformance |
| **Tool Discovery (`tools/list`)** | SUPPORTED | Exposes dynamically registered tools and JSON Schemas | Full Conformance |
| **Tool Invocation (`tools/call`)** | SUPPORTED | Validates parameters, executes governed pipeline | Full Conformance |
| **Tool Progress Notifications** | NOT IMPLEMENTED | Stdio streaming progress updates not exposed | Intentional Deferred |
| **Resources (`resources/list`, `read`)**| UNSUPPORTED | Read-only resources routed via capabilities | Not Implemented |
| **Prompts (`prompts/list`, `get`)** | UNSUPPORTED | Prompt templates not managed at control plane | Not Implemented |
| **Sampling (`sampling/createMessage`)** | UNSUPPORTED | TACP does not request agent completions | Out of Scope |
| **Roots (`roots/list`)** | UNSUPPORTED | Workspaces define filesystem roots internally | Not Implemented |
| **SSE Transport** | UNSUPPORTED | Stdio is the sole supported transport on Termux | Transport Limitation |

---

## 3. MCP Execution Pipeline Security Proof

When an LLM issues `tools/call` for `execution.request`:
```
MCP Client (e.g. Claude Desktop, Goose, custom agent)
  │  {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "execution.request", ...}}
  ▼
MCP Protocol Parser (src/tacp/access/mcp/protocol.py)
  │  JSON deserialization & schema validation
  ▼
MCP Server Adapter (src/tacp/access/mcp/server.py)
  │  Constructs RequestContext with Principal.local_agent("mcp-client")
  ▼
Tool Dispatcher (src/tacp/access/mcp/tools.py)
  │  Calls ExecutionService.execute_command(...)
  ▼
authoritative 16-Stage Governed Pipeline
  ├── Policy Engine (Denies or Requires Approval for restricted agent)
  ├── Approval Ticket Generation (if required)
  ├── Canonical ExecutionContract SHA-256 Hashing
  ├── Trusted Root Binary Resolution & Safe Allowlist Environment
  ├── SQLite WAL Pre-Persistence
  ├── ProcessExecutor Spawning (setsid, close_fds, DEVNULL stdin)
  ├── Model B Stream Governance
  └── Audit Hash Chain Append
```

**Security Invariant:** An MCP client cannot bypass approval requirements, cannot escape workspace roots, cannot inject arbitrary shell commands, cannot execute untrusted binaries, and cannot leak host secrets.
