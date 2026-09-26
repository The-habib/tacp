# TACP MCP Client Integration Examples

This document provides ready-to-run code snippets demonstrating how to connect to TACP Streamable HTTP MCP endpoints in various programming languages.

---

## 1. Python MCP SDK (`mcp` library)

Using the official Model Context Protocol Python SDK:

```bash
pip install mcp httpx
```

```python
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

TACP_URL = "https://unique-subdomain.trycloudflare.com/mcp"
BEARER_TOKEN = "<TACP_AUTH_TOKEN>"


async def main():
    headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}

    async with sse_client(TACP_URL, headers=headers) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # 1. Initialize session
            await session.initialize()
            print("Connected to TACP!")

            # 2. List available tools
            tools_result = await session.list_tools()
            print(f"Discovered {len(tools_result.tools)} tools:")
            for tool in tools_result.tools:
                print(f" - {tool.name}: {tool.description}")

            # 3. Call system.inspect
            system_info = await session.call_tool("system.inspect", arguments={})
            print("\nSystem Inspection Result:")
            print(system_info.content[0].text)

            # 4. List registered workspaces
            workspaces = await session.call_tool("workspace.list", arguments={})
            print("\nRegistered Workspaces:")
            print(workspaces.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 2. TypeScript MCP SDK (`@modelcontextprotocol/sdk`)

Using the official Node.js / TypeScript MCP SDK:

```bash
npm install @modelcontextprotocol/sdk
```

```typescript
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { SSEClientTransport } from "@modelcontextprotocol/sdk/client/sse.js";

const TACP_URL = new URL("https://unique-subdomain.trycloudflare.com/mcp");
const BEARER_TOKEN = "<TACP_AUTH_TOKEN>";

async function run() {
  const transport = new SSEClientTransport(TACP_URL, {
    requestInit: {
      headers: {
        Authorization: `Bearer ${BEARER_TOKEN}`,
      },
    },
  });

  const client = new Client(
    { name: "typescript-tacp-client", version: "1.0.0" },
    { capabilities: {} }
  );

  await client.connect(transport);
  console.log("Connected to TACP server via Streamable HTTP!");

  // List tools
  const tools = await client.listTools();
  console.log(`Found ${tools.tools.length} available tools.`);

  // Call system.inspect
  const result = await client.callTool({
    name: "system.inspect",
    arguments: {},
  });
  console.log("System Inspection Result:", result.content);
}

run().catch(console.error);
```

---

## 3. Pure Python (Zero Dependencies, Standard Library)

Connect to TACP without installing any third-party packages:

```python
import json
import urllib.request

TACP_URL = "https://unique-subdomain.trycloudflare.com/mcp"
TOKEN = "<TACP_AUTH_TOKEN>"


def mcp_call(method: str, params: dict, req_id: int = 1) -> dict:
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        TACP_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN}",
        },
        method="POST",
    )

    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


# Handshake
init_resp = mcp_call("initialize", {"protocolVersion": "2026-07-28"}, req_id=1)
print("Handshake:", init_resp["result"]["serverInfo"])

# Call tool
call_resp = mcp_call("tools/call", {"name": "system.inspect", "arguments": {}}, req_id=2)
content = json.loads(call_resp["result"]["content"][0]["text"])
print("Android Battery Status:", content.get("battery", "N/A"))
print("OS Release:", content.get("release", "N/A"))
```

---

## 4. Workstation cURL / Shell Script

```bash
#!/usr/bin/env bash
ENDPOINT="https://unique-subdomain.trycloudflare.com/mcp"
TOKEN="<TACP_AUTH_TOKEN>"

# 1. Initialize
curl -s -X POST "$ENDPOINT" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2026-07-28"}}' | jq .

# 2. Call fs.list in registered workspace
curl -s -X POST "$ENDPOINT" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"fs.list","arguments":{"workspace_id":"termux-home"}}}' | jq .
```
