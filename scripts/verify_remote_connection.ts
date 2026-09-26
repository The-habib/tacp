/**
 * Generic TypeScript MCP Remote Verification Client.
 *
 * Uses the official Model Context Protocol TypeScript SDK (@modelcontextprotocol/sdk)
 * to verify remote MCP Streamable HTTP connectivity.
 *
 * Usage:
 *   npx tsx scripts/verify_remote_connection.ts --url https://<HOST>/mcp [--token <TOKEN>]
 */

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

async function main() {
  const args = process.argv.slice(2);
  let url = process.env.TACP_URL || "";
  let token = process.env.TACP_TOKEN || "";

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--url" && i + 1 < args.length) {
      url = args[i + 1];
    } else if (args[i] === "--token" && i + 1 < args.length) {
      token = args[i + 1];
    }
  }

  if (!url) {
    console.error("Usage: node scripts/verify_remote_connection.js --url https://<HOST>/mcp [--token <TOKEN>]");
    process.exit(1);
  }

  const endpointUrl = new URL(url.endsWith("/mcp") ? url : `${url}/mcp`);

  console.log("============================================================");
  console.log(" TACP Remote MCP Interoperability Verifier (TypeScript)     ");
  console.log(` Target Endpoint: ${endpointUrl.toString()}`);
  console.log("============================================================");

  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token.trim()}`;
  }

  const transport = new StreamableHTTPClientTransport(endpointUrl, {
    requestInit: {
      headers: headers,
    },
  });

  const client = new Client(
    { name: "verify-remote-ts", version: "1.0.0" },
    { capabilities: {} }
  );

  console.log("[1/3] Connecting and initializing MCP session...");
  await client.connect(transport);
  console.log("      [PASS] Successfully initialized MCP session");

  console.log("[2/3] Calling tools/list...");
  const toolsResult = await client.listTools();
  console.log(`      [PASS] Discovered ${toolsResult.tools.length} available tools`);

  console.log("[3/3] Calling tool system.inspect...");
  const inspectResult = await client.callTool({
    name: "system.inspect",
    arguments: {},
  });
  console.log("      [PASS] Tool execution succeeded");

  console.log("============================================================");
  console.log(" VERIFICATION RESULT: PASS (All stages succeeded)");
  console.log("============================================================\n");

  await client.close();
  process.exit(0);
}

main().catch((err) => {
  console.error(`[FAIL] Verification error: ${err.message || err}`);
  process.exit(1);
});
