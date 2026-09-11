# Evidence: Remote Tool Surface & Exposure Audit

## Minimal Semantic Tool Surface
Under the `REMOTE_READ_ONLY` profile, TACP dynamically filters the MCP tool catalog. Mutating, batch, and execution tools are completely pruned from `tools/list`:

### Exposed Capabilities ($R_0$ Observation Only - 13 Tools)
1. `system.inspect`: Query system architecture, CPU, memory, platform.
2. `system.health`: Check database health, system load, status.
3. `system.version`: Report TACP version and protocol capabilities.
4. `capabilities.list`: List available registered capabilities.
5. `workspace.list`: List registered workspaces and their root paths.
6. `workspace.inspect`: Retrieve detailed statistics on a workspace.
7. `fs.list`: Safely list entries in a workspace directory.
8. `fs.stat`: Query metadata and permissions of a workspace path.
9. `fs.read`: Read contents of a non-secret workspace file (bounded).
10. `fs.search`: Search for string queries within workspace files.
11. `process.list`: Query running processes with bounded output.
12. `process.inspect`: Retrieve details on a specific PID.
13. `audit.recent`: View recent audit log history.

### Hidden / Forbidden Capabilities (Strictly Pruned)
* `workspace.patch` (Hidden & Denied)
* `workspace.patch_batch` (Hidden & Denied)
* `workspace.rollback` (Hidden & Denied)
* `execution.request` (Hidden & Denied)
* `audit.verify_integrity` (Hidden & Denied to remote callers)

## Verification
Verified in `tests/unit/test_remote_governance.py::TestToolExposureAudit::test_remote_read_only_exposes_only_r0_tools` and `tests/integration/test_remote_tunnel.py::test_mcp_handshake_remote_mode`.
