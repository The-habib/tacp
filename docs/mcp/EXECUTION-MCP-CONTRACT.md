# TACP Execution MCP Contract Specification
## Tool Schema, Protocols & Error Envelopes for `execution.request`

- **Standard:** TACP-MCP-004-EXEC
- **Status:** APPROVED MCP SPECIFICATION (GATE A)
- **Supported MCP Revisions:** `2026-07-28` (Primary) & `2024-11-05` (Legacy)

---

## 1. Tool Declaration & Schema

When `config.execution_enabled = True`, `execution.request` is registered in `McpToolRegistry` and emitted in `tools/list`:

```json
{
  "name": "execution.request",
  "description": "Execute a governed, policy-controlled operating system command with strict arguments, workspace containment, and bounded output.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "workspace_id": {
        "type": "string",
        "description": "ID of the target active workspace where the command will execute."
      },
      "executable": {
        "type": "string",
        "description": "Deterministic executable binary name (e.g. 'printf') or path."
      },
      "argv": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Ordered array of string arguments passed to the executable. Shell metacharacters are treated as literal strings."
      },
      "cwd": {
        "type": "string",
        "description": "Optional relative subpath within the workspace to run in. Defaults to workspace root."
      },
      "environment": {
        "type": "object",
        "additionalProperties": { "type": "string" },
        "description": "Optional dictionary of safe environment variables. Unsafe and secret variables are stripped."
      },
      "timeout_seconds": {
        "type": "integer",
        "description": "Requested execution timeout in seconds (default: 15, maximum: 60)."
      },
      "dry_run": {
        "type": "boolean",
        "description": "If true, simulates policy checks, argument resolution, and contract hashing without spawning a process."
      },
      "approval_token": {
        "type": "string",
        "description": "Human approval token required for non-dry-run execution."
      }
    },
    "required": ["workspace_id", "executable", "argv"]
  }
}
```

---

## 2. Success Response Format

When execution succeeds (or dry-run finishes), the tool response returns standard MCP content blocks:

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\n  \"execution_id\": \"exec-9876543210ab\",\n  \"status\": \"SUCCEEDED\",\n  \"exit_code\": 0,\n  \"duration_ms\": 42,\n  \"stdout\": \"hello world\\n\",\n  \"stderr\": \"\",\n  \"stdout_truncated\": false,\n  \"stderr_truncated\": false,\n  \"timed_out\": false,\n  \"cancelled\": false,\n  \"contract_hash\": \"a3b1c2...\"\n}"
    }
  ],
  "isError": false,
  "_meta": {
    "trace_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "request_id": "c9a646d3-9c61-4cfa-89df-15efd4b68e0e"
  }
}
```

---

## 3. Structured Error & Approval Envelopes

### Scenario A: Human Approval Required (Status 403 / APPROVAL_REQUIRED)
When an agent calls `execution.request` with `dry_run=False` and no approval token, TACP responds with an approval envelope containing the pending ticket details:

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\n  \"error\": \"TacpApprovalRequiredError\",\n  \"code\": \"APPROVAL_REQUIRED\",\n  \"message\": \"Execution of 'printf' requires explicit human approval\",\n  \"ticket\": {\n    \"ticket_id\": \"appr-8f12a4b9\",\n    \"token\": \"tacp_appr_8f93e...\",\n    \"contract_hash\": \"a3b1c2...\",\n    \"expires_at\": \"2026-09-11T12:30:00Z\"\n  }\n}"
    }
  ],
  "isError": true
}
```

### Scenario B: Feature Flag Disabled / Policy Denied
When `config.execution_enabled = False` or policy rejects the binary:

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\n  \"error\": \"TacpSecurityError\",\n  \"code\": \"POLICY_DENIED\",\n  \"message\": \"Access denied: Command execution is disabled in TACP configuration\"\n}"
    }
  ],
  "isError": true
}
```
