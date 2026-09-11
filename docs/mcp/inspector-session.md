# MCP Inspector Verification Session Log

- **Date**: 2026-09-11
- **Inspector Tool**: `@modelcontextprotocol/inspector` v2.6.0 (running on Node.js v26.4.0 in Termux `aarch64`)
- **Server Under Test**: `tacp serve` (TACP v0.1.0-rc.1)
- **Transport**: Standard I/O (stdio)
- **Conformance Status**: **PASSED** (13/13 tools strictly validated, zero schema errors)

---

## 1. Handshake and Protocol Negotiation

```bash
node /data/data/com.termux/files/usr/bin/mcp-inspector --cli /data/data/com.termux/files/home/projects/tacp/.venv/bin/tacp serve --method initialize
```

### Output:
```json
{
  "serverInfo": {
    "name": "tacp",
    "version": "0.1.0-rc.1"
  },
  "protocolVersion": "2025-11-25",
  "capabilities": {
    "tools": {}
  },
  "instructions": "TACP (Termux AI Control Plane) is a strictly read-only MCP server."
}
```
*Note: Inspector requested protocol version `2025-11-25`. TACP's protocol negotiator dynamically matched this known protocol version, preserving backward compatibility while offering `2026-07-28` modern capabilities.*

---

## 2. Tool Discovery (`tools/list` with `--strict` schema validation)

```bash
node /data/data/com.termux/files/usr/bin/mcp-inspector --cli /data/data/com.termux/files/home/projects/tacp/.venv/bin/tacp serve --method tools/list --strict
```

### Output:
```json
{
  "tools": [
    {
      "name": "system.inspect",
      "description": "Inspect host system, kernel, CPU architecture, memory, and Termux details",
      "inputSchema": {
        "type": "object",
        "properties": {}
      }
    },
    {
      "name": "system.health",
      "description": "Check TACP subsystem health, storage margins, and database connectivity",
      "inputSchema": {
        "type": "object",
        "properties": {}
      }
    },
    {
      "name": "system.version",
      "description": "Return TACP version and supported MCP protocol specification",
      "inputSchema": {
        "type": "object",
        "properties": {}
      }
    },
    {
      "name": "capabilities.list",
      "description": "List all available TACP capabilities and their parameter schemas",
      "inputSchema": {
        "type": "object",
        "properties": {}
      }
    },
    {
      "name": "workspace.list",
      "description": "List all registered workspace roots and their status",
      "inputSchema": {
        "type": "object",
        "properties": {}
      }
    },
    {
      "name": "workspace.inspect",
      "description": "Inspect statistics, file counts, and git repository status of a workspace",
      "inputSchema": {
        "type": "object",
        "properties": {
          "workspace_id": {
            "type": "string"
          }
        },
        "required": [
          "workspace_id"
        ]
      }
    },
    {
      "name": "fs.list",
      "description": "List directory entries inside an authorized workspace root with metadata",
      "inputSchema": {
        "type": "object",
        "properties": {
          "workspace_id": {
            "type": "string"
          },
          "subpath": {
            "type": "string"
          }
        },
        "required": [
          "workspace_id"
        ]
      }
    },
    {
      "name": "fs.stat",
      "description": "Get detailed metadata, permissions, and classification for a file or directory",
      "inputSchema": {
        "type": "object",
        "properties": {
          "workspace_id": {
            "type": "string"
          },
          "subpath": {
            "type": "string"
          }
        },
        "required": [
          "workspace_id",
          "subpath"
        ]
      }
    },
    {
      "name": "fs.read",
      "description": "Safely read file content with output size truncation and secret protection",
      "inputSchema": {
        "type": "object",
        "properties": {
          "workspace_id": {
            "type": "string"
          },
          "subpath": {
            "type": "string"
          }
        },
        "required": [
          "workspace_id",
          "subpath"
        ]
      }
    },
    {
      "name": "fs.search",
      "description": "Search file content within a workspace using substring or regex pattern",
      "inputSchema": {
        "type": "object",
        "properties": {
          "workspace_id": {
            "type": "string"
          },
          "query": {
            "type": "string"
          },
          "subpath": {
            "type": "string"
          }
        },
        "required": [
          "workspace_id",
          "query"
        ]
      }
    },
    {
      "name": "process.list",
      "description": "List running processes owned by the current Termux user",
      "inputSchema": {
        "type": "object",
        "properties": {}
      }
    },
    {
      "name": "process.inspect",
      "description": "Inspect command line, memory, and status of a specific user process PID",
      "inputSchema": {
        "type": "object",
        "properties": {
          "pid": {
            "type": "integer"
          }
        },
        "required": [
          "pid"
        ]
      }
    },
    {
      "name": "audit.recent",
      "description": "Retrieve recent tamper-evident audit events and authorization decisions",
      "inputSchema": {
        "type": "object",
        "properties": {
          "limit": {
            "type": "integer"
          }
        }
      }
    }
  ]
}
```
*Result: Exit code 0. Zero schema violations reported by `--strict`.*

---

## 3. Tool Execution: `system.inspect`

```bash
node /data/data/com.termux/files/usr/bin/mcp-inspector --cli /data/data/com.termux/files/home/projects/tacp/.venv/bin/tacp serve --method tools/call --tool-name system.inspect
```

### Output:
```json
{
  "content": [
    {
      "type": "text",
      "text": "{\n  \"os\": \"Android\",\n  \"node\": \"localhost\",\n  \"release\": \"16\",\n  \"version\": \"#1 SMP PREEMPT Thu Jun 11 04:32:26 UTC 2026\",\n  \"machine\": \"aarch64\",\n  \"arch\": \"aarch64\",\n  \"kernel\": \"16\",\n  \"python_version\": \"3.14.6\",\n  \"termux\": {\n    \"is_termux\": true,\n    \"version\": \"0.118.3\",\n    \"prefix\": \"/data/data/com.termux/files/usr\"\n  },\n  \"memory\": {\n    \"total_mb\": 7305,\n    \"free_mb\": 1283\n  },\n  \"storage\": {\n    \"total_bytes\": 110291922944,\n    \"used_bytes\": 103534354432,\n    \"free_bytes\": 6623350784,\n    \"total_mb\": 105182,\n    \"free_mb\": 6316,\n    \"used_percent\": 93.9\n  }\n}"
    }
  ],
  "isError": false
}
```

---

## 4. Tool Execution: `fs.read` (Authorized Path)

```bash
node /data/data/com.termux/files/usr/bin/mcp-inspector --cli /data/data/com.termux/files/home/projects/tacp/.venv/bin/tacp serve --method tools/call --tool-name fs.read --tool-arg workspace_id=286bff87 --tool-arg subpath=README.md
```

### Output:
```json
{
  "content": [
    {
      "type": "text",
      "text": "{\n  \"path\": \"README.md\",\n  \"content\": \"# TACP \\u2014 Termux AI Control Plane\\n...\",\n  \"bytes_read\": 1168,\n  \"truncated\": false,\n  \"total_bytes\": 1168,\n  \"total_size_bytes\": 1168,\n  \"workspace_id\": \"286bff87\"\n}"
    }
  ],
  "isError": false
}
```

---

## 5. Security & Boundary Rejection: Path Traversal Attempt

```bash
node /data/data/com.termux/files/usr/bin/mcp-inspector --cli /data/data/com.termux/files/home/projects/tacp/.venv/bin/tacp serve --method tools/call --tool-name fs.read --tool-arg workspace_id=286bff87 --tool-arg subpath=../../etc/passwd
```

### Output:
```json
{
  "content": [
    {
      "type": "text",
      "text": "Error (OUTSIDE_WORKSPACE): Path '../../etc/passwd' escapes authorized workspace boundary"
    }
  ],
  "isError": true
}
```
*Result: Exit code 5 (inspector flags tool error), TACP correctly returned structured error and preserved security boundaries.*
