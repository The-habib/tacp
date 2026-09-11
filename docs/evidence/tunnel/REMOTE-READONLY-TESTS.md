# Evidence: Remote Read-Only Execution Tests

## Execution Trace (Remote AI Principal)
All tests executed with `Principal.remote_ai("chatgpt-session-42")`:

### 1. `system.version`
* **Request**: `{"name": "system.version", "arguments": {}}`
* **Response**:
  ```json
  {
    "tacp_version": "0.4.0-rc.1",
    "mcp_protocol_version": "2026-07-28",
    "supported_mcp_versions": ["2026-07-28", "2024-11-05"],
    "phase": "3.0",
    "mode": "GOVERNED"
  }
  ```

### 2. `fs.read`
* **Request**: `{"name": "fs.read", "arguments": {"workspace_id": "...", "subpath": "app.py"}}`
* **Response**:
  ```json
  {
    "path": "app.py",
    "content": "print('hello world')\n",
    "bytes_read": 21,
    "truncated": false,
    "total_bytes": 21,
    "total_size_bytes": 21
  }
  ```

### 3. `workspace.list`
* **Request**: `{"name": "workspace.list", "arguments": {}}`
* **Response**: Successfully returns list of active workspaces.

### 4. `process.list`
* **Request**: `{"name": "process.list", "arguments": {}}`
* **Response**: Successfully returns bounded process table with sanitized PIDs.

## Test Validation
Verified in `tests/integration/test_remote_tunnel.py::test_mcp_remote_ai_tool_call_roundtrip`.
