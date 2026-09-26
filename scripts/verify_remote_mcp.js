#!/usr/bin/env node
/**
 * Official TACP Remote MCP Protocol Verification Client (Node.js/TypeScript).
 *
 * Uses the official Model Context Protocol SDK (@modelcontextprotocol/sdk)
 * to verify remote MCP Streamable HTTP connectivity over network endpoints.
 *
 * Usage:
 *   node scripts/verify_remote_mcp.js --url https://<HOST>/mcp [--token <TOKEN>]
 */

const path = require("path");

let Client, StreamableHTTPClientTransport;
try {
  const sdkBase = path.join(__dirname, "test_ts", "node_modules", "@modelcontextprotocol", "sdk", "dist", "cjs");
  Client = require(path.join(sdkBase, "client", "index.js")).Client;
  StreamableHTTPClientTransport = require(path.join(sdkBase, "client", "streamableHttp.js")).StreamableHTTPClientTransport;
} catch (e) {
  try {
    Client = require("@modelcontextprotocol/sdk/client/index.js").Client;
    StreamableHTTPClientTransport = require("@modelcontextprotocol/sdk/client/streamableHttp.js").StreamableHTTPClientTransport;
  } catch (e2) {
    console.error("[ERROR] Failed to load @modelcontextprotocol/sdk. Ensure npm dependencies are installed in scripts/test_ts.");
    process.exit(1);
  }
}

async function main() {
  const args = process.argv.slice(2);
  let url = process.env.TACP_MCP_URL || process.env.TACP_URL || "";
  let token = process.env.TACP_MCP_TOKEN || process.env.TACP_TOKEN || "";

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--url" && i + 1 < args.length) {
      url = args[i + 1];
    } else if (args[i] === "--token" && i + 1 < args.length) {
      token = args[i + 1];
    }
  }

  if (!url) {
    console.error("[ERROR] Missing MCP URL. Usage: node scripts/verify_remote_mcp.js --url https://<HOST>/mcp [--token <TOKEN>]");
    process.exit(1);
  }

  const endpointUrl = new URL(url.endsWith("/mcp") ? url : `${url}/mcp`);

  console.log("============================================================");
  console.log(" TACP Remote MCP Protocol Verification Suite (TypeScript/Node)");
  console.log(` Target Endpoint: ${endpointUrl.toString()}`);
  console.log(` Auth Token     : ${token ? "[PROVIDED: " + token.slice(0, 12) + "...]" : "[NONE]"}`);
  console.log("============================================================");

  const results = [];
  function log(step, ok, details = "") {
    results.push({ step, ok, details });
    const tag = ok ? "[PASS]" : "[FAIL]";
    console.log(`${tag} ${step}`);
    if (details) {
      console.log(`       -> ${details}`);
    }
  }

  const headers = {
    "User-Agent": "TACP-Official-Node-MCP-Client/1.0",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token.trim()}`;
  }

  const transport = new StreamableHTTPClientTransport(endpointUrl, {
    requestInit: {
      headers: headers,
    },
  });

  const client = new Client(
    { name: "tacp-node-verifier", version: "1.0.0" },
    { capabilities: {} }
  );

  try {
    // 1. Connection & MCP Initialize
    console.log("[*] Initializing MCP session...");
    await client.connect(transport);
    log("1. MCP Initialize Handshake", true, "Connected and negotiated protocol session");

    // 2. Tool Discovery
    console.log("[*] Discovering tools...");
    const toolsResult = await client.listTools();
    const tools = toolsResult.tools || [];
    log(
      `2. Tool Discovery (tools/list: ${tools.length} tools)`,
      tools.length >= 10,
      `Sample: ${tools.slice(0, 5).map((t) => t.name).join(", ")}...`
    );

    // 3. Resource Discovery
    console.log("[*] Discovering resources...");
    try {
      const resResult = await client.listResources();
      const resources = resResult.resources || [];
      log(
        `3. Resource Cataloging (resources/list: ${resources.length} resources)`,
        resources.length >= 4,
        `Sample URIs: ${resources.slice(0, 4).map((r) => r.uri).join(", ")}`
      );
    } catch (e) {
      log("3. Resource Cataloging (resources/list)", false, e.message);
    }

    // 4. Safe Tool Invocation: system.inspect
    console.log("[*] Calling safe tool: system.inspect...");
    try {
      const callResult = await client.callTool({
        name: "system.inspect",
        arguments: {},
      });
      const content = callResult.content;
      const snippet = content && content[0] ? content[0].text.slice(0, 100).replace(/\n/g, " ") : "";
      log("4. Safe Tool Call (system.inspect)", !callResult.isError, `Output: ${snippet}...`);
    } catch (e) {
      log("4. Safe Tool Call (system.inspect)", false, e.message);
    }

    // 5. Safe Tool Invocation: device.info
    console.log("[*] Calling safe tool: device.info...");
    try {
      const callResult = await client.callTool({
        name: "device.info",
        arguments: {},
      });
      const content = callResult.content;
      const snippet = content && content[0] ? content[0].text.slice(0, 100).replace(/\n/g, " ") : "";
      log("5. Safe Tool Call (device.info)", !callResult.isError, `Output: ${snippet}...`);
    } catch (e) {
      log("5. Safe Tool Call (device.info)", false, e.message);
    }

    await client.close();

    const passed = results.filter((r) => r.ok).length;
    console.log("============================================================");
    console.log(` TS/NODE VERIFICATION RESULT: ${passed}/${results.length} Checks PASSED`);
    console.log("============================================================");
    process.exit(passed === results.length ? 0 : 1);
  } catch (err) {
    log("MCP Client Lifecycle", false, `Fatal error: ${err.message}`);
    console.error(err);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error("Unhandled rejection:", err);
  process.exit(1);
});
