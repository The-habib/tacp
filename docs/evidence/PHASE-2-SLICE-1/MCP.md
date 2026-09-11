# Phase 2 — Vertical Slice 1: MCP Protocol Verification Report

**MCP Specification:** 2026-07-28 (with backwards compatibility for 2024-11-05)  
**Transport:** Standard I/O (stdio) via JSON-RPC 2.0  
**Tool Added:** `workspace.patch` (governed mutating capability)

---

## 1. Tool Visibility & Governance

Under TACP security specifications, mutating tools must not be exposed when the server is operating in read-only mode:

### 1.1 Read-Only State (`mutation_enabled = false` / default)
- **Tool List Output:** Exactly 13 tools exposed.
- `workspace.patch` is **omitted** from `tools/list`.
- Direct invocation returns `POLICY_DENIED` (-32000).

### 1.2 Mutating State (`mutation_enabled = true` / `TACP_MUTATION_ENABLED=1`)
- **Tool List Output:** Exactly 14 tools exposed.
- `workspace.patch` is present with complete input schema.

---

## 2. Tool Schema: `workspace.patch`

```json
{
  "name": "workspace.patch",
  "description": "Apply a governed unified diff patch to a text file within an authorized workspace",
  "inputSchema": {
    "type": "object",
    "properties": {
      "workspace_id": {
        "type": "string",
        "description": "ID of the target workspace"
      },
      "subpath": {
        "type": "string",
        "description": "Relative path to the target text file within the workspace"
      },
      "patch_content": {
        "type": "string",
        "description": "Unified diff content to apply"
      },
      "base_checksum": {
        "type": "string",
        "description": "Expected SHA-256 checksum of the target file prior to patching"
      },
      "dry_run": {
        "type": "boolean",
        "description": "If true, simulates the patch and returns diff stats without modifying the file"
      },
      "approval_token": {
        "type": "string",
        "description": "Human approval token required for live mutations"
      }
    },
    "required": ["workspace_id", "subpath", "patch_content", "base_checksum"]
  }
}
```

---

## 3. Protocol Invariants & Error Mapping

| Condition | JSON-RPC 2.0 Response | Error Code |
| :--- | :--- | :--- |
| Missing required argument | Tool Error / Exception | `INVALID_INPUT` |
| Dry run simulation | Successful tool result with `status: SIMULATED` | N/A |
| Live run without token | Error with ticket token in message | `APPROVAL_REQUIRED` |
| Optimistic concurrency mismatch | Error with checksum mismatch info | `CONFLICT` |
| Path outside workspace | Security error | `OUTSIDE_WORKSPACE` |
