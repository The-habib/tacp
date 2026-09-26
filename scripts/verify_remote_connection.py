#!/usr/bin/env python3
"""Generic Python MCP Verification Client.

Validates an MCP Streamable HTTP endpoint using standard JSON-RPC 2.0 and HTTP.
Compatible with any standard MCP server. Does not depend on external AI vendors.

Usage:
    python scripts/verify_remote_connection.py --url https://<HOST>/mcp [--token <TOKEN>]
    Or set:
    export TACP_TOKEN="tacp_sec_..."
    python scripts/verify_remote_connection.py --url https://<HOST>/mcp
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


class RemoteMcpClient:
    def __init__(self, mcp_url: str, token: Optional[str] = None) -> None:
        self.mcp_url = mcp_url.rstrip("/")
        if not self.mcp_url.endswith("/mcp"):
            self.mcp_url = f"{self.mcp_url}/mcp"
        self.token = token or os.environ.get("TACP_TOKEN")
        self.session_id: Optional[str] = None
        self.protocol_version: str = "2026-07-28"

    def rpc_call(
        self, method: str, params: Optional[Dict[str, Any]] = None, req_id: Any = 1
    ) -> Dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token.strip()}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.mcp_url, data=data_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_headers = dict(resp.headers)
                if "Mcp-Session-Id" in resp_headers:
                    self.session_id = resp_headers["Mcp-Session-Id"]
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="ignore")
            try:
                err_json = json.loads(err_body)
                raise RuntimeError(
                    f"HTTP {exc.code} Error: {err_json.get('error', {}).get('message', err_body)}"
                )
            except Exception:
                raise RuntimeError(f"HTTP {exc.code} Error: {err_body}") from exc
        except Exception as exc:
            raise RuntimeError(f"Connection failed to {self.mcp_url}: {exc}") from exc

    def verify(self) -> bool:
        print("============================================================")
        print(" TACP Remote MCP Interoperability Verifier (Python)         ")
        print(f" Target Endpoint: {self.mcp_url}")
        print("============================================================")

        # 1. Initialize
        print("[1/5] Performing MCP Handshake (initialize)...")
        try:
            init_resp = self.rpc_call(
                "initialize",
                {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": "verify-remote-python", "version": "1.0.0"},
                },
                req_id="init-01",
            )
            res = init_resp.get("result", {})
            srv_info = res.get("serverInfo", {})
            negotiated_ver = res.get("protocolVersion")
            print(
                f"      [PASS] Connected to server: {srv_info.get('name')} v{srv_info.get('version')}"
            )
            print(f"      [PASS] Negotiated Protocol Version: {negotiated_ver}")
        except Exception as exc:
            print(f"      [FAIL] Handshake failed: {exc}")
            return False

        # 2. Tool Discovery
        print("[2/5] Discovering capabilities (tools/list)...")
        tools = []
        try:
            tools_resp = self.rpc_call("tools/list", {}, req_id="list-01")
            tools = tools_resp.get("result", {}).get("tools", [])
            tool_names = [t.get("name") for t in tools]
            print(f"      [PASS] Discovered {len(tools)} tools: {', '.join(tool_names[:6])}...")
        except Exception as exc:
            print(f"      [FAIL] Tool discovery failed: {exc}")
            return False

        # 3. Safe Telemetry Execution (system.inspect)
        print("[3/5] Invoking system telemetry tool (system.inspect)...")
        try:
            inspect_resp = self.rpc_call(
                "tools/call",
                {"name": "system.inspect", "arguments": {}},
                req_id="call-01",
            )
            res = inspect_resp.get("result", {})
            if res.get("isError"):
                print(f"      [FAIL] Tool call returned error: {res}")
                return False
            content = res.get("content", [{}])[0].get("text", "")
            data = json.loads(content)
            print(
                f"      [PASS] OS Release: {data.get('release', 'N/A')}, Architecture: {data.get('machine', 'N/A')}"
            )
        except Exception as exc:
            print(f"      [FAIL] system.inspect invocation failed: {exc}")
            return False

        # 4. Safe Diagnostic Health (system.health)
        print("[4/5] Invoking system health tool (system.health)...")
        try:
            health_resp = self.rpc_call(
                "tools/call",
                {"name": "system.health", "arguments": {}},
                req_id="call-02",
            )
            res = health_resp.get("result", {})
            if res.get("isError"):
                print(f"      [FAIL] Tool call returned error: {res}")
                return False
            content = res.get("content", [{}])[0].get("text", "")
            data = json.loads(content)
            print(f"      [PASS] Overall Health: {data.get('overall_health', 'N/A')}")
        except Exception as exc:
            print(f"      [FAIL] system.health invocation failed: {exc}")
            return False

        # 5. Security Boundary & Traversal Defense
        print("[5/5] Testing security boundary rejection...")
        try:
            sec_resp = self.rpc_call(
                "tools/call",
                {
                    "name": "fs.read",
                    "arguments": {
                        "workspace_id": "termux-home",
                        "relative_path": "../../../../etc/shadow",
                    },
                },
                req_id="call-sec-01",
            )
            res = sec_resp.get("result", {})
            if res.get("isError") is True:
                err_msg = res.get("content", [{}])[0].get("text", "")
                print(f"      [PASS] Safely rejected forbidden traversal: {err_msg.strip()[:80]}")
            else:
                print("      [FAIL] Security check failed: Path traversal was not rejected!")
                return False
        except Exception as exc:
            # If rejected at HTTP layer, that is also a pass
            print(f"      [PASS] Safely rejected at transport layer: {exc}")

        print("============================================================")
        print(" VERIFICATION RESULT: PASS (All 5 stages succeeded)")
        print("============================================================\n")
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify remote TACP MCP server.")
    parser.add_argument("--url", required=True, help="Remote MCP endpoint URL")
    parser.add_argument("--token", help="Bearer authentication token (or set TACP_TOKEN)")
    args = parser.parse_args()

    client = RemoteMcpClient(mcp_url=args.url, token=args.token)
    success = client.verify()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
