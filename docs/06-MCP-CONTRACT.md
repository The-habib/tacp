# TACP Model Context Protocol (MCP) Contract

**Status**: SKELETON / PLANNED  
**Protocol Version**: MCP Specification (Compatible with `@modelcontextprotocol/sdk` 1.30.0 / Python `mcp` 2.2.0)  

---

## 1. Transport Specifications

TACP will support standard MCP transports:
1. **Stdio Transport**: Used for local subprocess orchestration by Antigravity CLI and terminal runners.
2. **SSE / HTTP Transport**: Used for remote connections over secure tunnels.

---

## 2. Baseline Tool Specifications [PLANNED]

### Tool: `inspect_workspace` (First Slice)
- **Description**: Returns structured information about an authorized workspace.
- **Input Schema**:
  ```json
  {
    type: object,
    properties: {
      workspace_id: { type: string },
      subpath: { type: string, default:  }
    },
    required: [workspace_id]
  }
  ```
- **Output**: JSON object with directory listing, file counts, and git status.

---

## 3. Safety Guarantees

Every tool invocation will:
- Pass through the Control Plane policy filter.
- Return structured error codes rather than raw stack traces.
- Be captured in the central audit trail.
