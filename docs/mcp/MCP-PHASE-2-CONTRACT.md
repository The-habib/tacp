# TACP Phase 2 Model Context Protocol (MCP) Contract

**Document:** `docs/mcp/MCP-PHASE-2-CONTRACT.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**MCP Lead:** Antigravity MCP Protocol Lead  
**Specification Baseline:** MCP Specification `2026-07-28`  
**Date:** September 11, 2026  

---

## 1. Protocol Architecture & Invariants

1. **MCP Handler as Pure Protocol Adapter**: MCP handlers receive JSON-RPC messages, deserialize arguments, pass requests into the TACP application services, format responses, and return them. **MCP handlers never execute OS primitives directly**.
2. **Current Specification Fidelity (`2026-07-28`)**: TACP natively implements stateless discovery (`server/discover`), per-request metadata (`_meta`), caching scopes (`cacheScope: "public"`), and standardized execution completion (`resultType: "complete"`).
3. **No Synthetic Tasks**: Since the official Python SDK v2.2.0 does not implement MCP Tasks, long-running operations are exposed via standard, typed MCP tools.

---

## 2. The MCP Tool Gate (Mandatory Pre-Flight Checklist)

No new capability or tool can be exposed in `tools/list` or handled in `tools/call` until all 10 gate requirements are satisfied and verified by automated tests:

```
[ ] 1. Strict Input JSON Schema defined with property descriptions and types
[ ] 2. Strict Output JSON Schema defined with typed result structures
[ ] 3. Policy rule registered in PolicyEngine with default-deny behavior
[ ] 4. Risk Level assigned (R0 to R5) and Autonomy Level mapped (L0 to L5)
[ ] 5. Resource Scope canonicalized and validated within jail
[ ] 6. Cryptographic AuditEvent emission implemented and tested
[ ] 7. Resource & Output Limits enforced (size, lines, timeout)
[ ] 8. Negative API surface tests passing (no write/exec bypass)
[ ] 9. Adversarial Security test cases added and passing
[ ] 10. MCP Inspector strict schema validation verified with 0 warnings
```

---

## 3. Phase 2 MCP Tool Catalog (Incremental by Slice)

### Slice 1 Tool: `tacp_workspace_patch` (`workspace.patch`)
- **Description**: Proposes or applies an atomic, explainable unified patch to a single file within an authorized workspace.
- **Input Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "workspace_id": { "type": "string", "description": "Target workspace ID" },
      "subpath": { "type": "string", "description": "Relative file path inside workspace" },
      "base_checksum": { "type": "string", "description": "SHA-256 hash of file before patch" },
      "patch_diff": { "type": "string", "description": "Unified diff content" },
      "dry_run": { "type": "boolean", "description": "If true, simulate diff without disk mutation", "default": false }
    },
    "required": ["workspace_id", "subpath", "base_checksum", "patch_diff"]
  }
  ```
- **Output Schema**:
  ```json
  {
    "type": "object",
    "properties": {
      "patch_id": { "type": "string" },
      "status": { "type": "string", "enum": ["APPLIED", "SIMULATED", "CONFLICT", "APPROVAL_REQUIRED", "DENIED", "FAILED"] },
      "subpath": { "type": "string" },
      "before_checksum": { "type": "string" },
      "after_checksum": { "type": "string" },
      "lines_added": { "type": "integer" },
      "lines_removed": { "type": "integer" },
      "audit_id": { "type": "string" }
    },
    "required": ["patch_id", "status", "subpath"]
  }
  ```

---

## 4. Error Code Mapping (JSON-RPC 2.0 to TACP Errors)

TACP internal domain errors map deterministically to JSON-RPC protocol error codes:

| TACP Error Code | JSON-RPC Code | JSON-RPC Message | Explanation |
|---|---|---|---|
| `PARSE_ERROR` | `-32700` | Parse error | Malformed JSON in request stream |
| `INVALID_REQUEST` | `-32600` | Invalid Request | Missing method, wrong version, invalid protocol |
| `METHOD_NOT_FOUND` | `-32601` | Method not found | Unknown JSON-RPC method |
| `INVALID_PARAMS` | `-32602` | Invalid params | Parameter schema validation failure |
| `INTERNAL_ERROR` | `-32603` | Internal error | Unexpected system fault (details suppressed) |
| `NOT_AUTHORIZED` | `-32001` | Access denied | Policy denied action or missing capability |
| `APPROVAL_REQUIRED` | `-32002` | Approval required | Action exceeds autonomy; approval ticket created |
| `OUTSIDE_WORKSPACE` | `-32003` | Path jailbreak | Target path escapes authorized workspace root |
| `CONFLICT` | `-32004` | State conflict | File modified on disk (base_checksum mismatch) |
| `RESOURCE_LIMIT` | `-32005` | Resource exhausted | Output size, memory, or timeout quota exceeded |
| `SECRET_PROTECTED` | `-32006` | Secret protected | Target file contains protected credentials |

Internal stack traces are **permanently suppressed** from JSON-RPC error responses to prevent information leakage.
