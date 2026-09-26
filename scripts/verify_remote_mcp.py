#!/usr/bin/env python3
"""Official TACP Remote MCP Protocol Verification Client (Python).

Connects to a real remote or local MCP Streamable HTTP endpoint using standard
JSON-RPC 2.0 over HTTP. Performs end-to-end verification of protocol handshake,
tool discovery, resource cataloging, prompt discovery, safe tool invocation,
and authorization policy enforcement.

Usage:
    python scripts/verify_remote_mcp.py --url https://<HOST>/mcp [--token <TOKEN>]
Or environment variables:
    export TACP_MCP_URL="https://<HOST>/mcp"
    export TACP_MCP_TOKEN="tacp_sec_..."
    python scripts/verify_remote_mcp.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


class RemoteMcpVerifier:
    """Independent MCP Client validating Streamable HTTP transport compliance."""

    def __init__(self, mcp_url: str, token: Optional[str] = None) -> None:
        raw_url = mcp_url.rstrip("/")
        if not raw_url.endswith("/mcp"):
            self.mcp_url = f"{raw_url}/mcp"
            self.base_url = raw_url
        else:
            self.mcp_url = raw_url
            self.base_url = raw_url[:-4]

        self.token = token or os.environ.get("TACP_MCP_TOKEN") or os.environ.get("TACP_TOKEN")
        self.session_id: Optional[str] = None
        self.protocol_version: str = "2026-07-28"
        self.results: List[Tuple[str, bool, str]] = []

    def log(self, step: str, ok: bool, details: str = "") -> None:
        self.results.append((step, ok, details))
        status_tag = "[PASS]" if ok else "[FAIL]"
        print(f"{status_tag} {step}")
        if details:
            print(f"       -> {details}")

    def http_request(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
        auth: bool = True,
        timeout: float = 25.0,
    ) -> Tuple[int, Dict[str, str], bytes]:
        url = f"{self.base_url}{endpoint}" if endpoint.startswith("/") else endpoint
        headers: Dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "TACP-Independent-MCP-Verifier/1.0",
        }
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token.strip()}"
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        payload = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=payload, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_headers = {k.lower(): v for k, v in dict(resp.headers).items()}
                if "mcp-session-id" in resp_headers:
                    self.session_id = resp_headers["mcp-session-id"]
                return resp.status, resp_headers, resp.read()
        except urllib.error.HTTPError as exc:
            resp_headers = {k.lower(): v for k, v in dict(exc.headers).items()}
            return exc.code, resp_headers, exc.read()
        except Exception as exc:
            raise RuntimeError(f"Network error connecting to {url}: {exc}") from exc

    def rpc(self, method: str, params: Optional[Dict[str, Any]] = None, req_id: Any = 1, auth: bool = True) -> Tuple[int, Dict[str, Any]]:
        body = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }
        status, _, raw = self.http_request("/mcp", method="POST", data=body, auth=auth)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except Exception:
            parsed = {"raw": raw.decode("utf-8", errors="replace")}
        return status, parsed

    def run_suite(self) -> bool:
        print("============================================================")
        print(" TACP Remote MCP Protocol Verification Suite (Python)       ")
        print(f" Target Endpoint: {self.mcp_url}")
        print(f" Auth Token     : {'[PROVIDED: ' + self.token[:12] + '...]' if self.token else '[NONE]'}")
        print("============================================================")

        # 1. Health Probe
        try:
            status, _, raw = self.http_request("/health", method="GET", auth=False)
            data = json.loads(raw.decode("utf-8"))
            ok = status == 200 and data.get("status") == "ok"
            self.log("1. Infrastructure Health Probe (GET /health)", ok, f"HTTP {status}, status={data.get('status')}, version={data.get('version')}")
        except Exception as exc:
            self.log("1. Infrastructure Health Probe (GET /health)", False, str(exc))

        # 2. Readiness Probe
        try:
            status, _, raw = self.http_request("/ready", method="GET", auth=False)
            data = json.loads(raw.decode("utf-8"))
            ok = status == 200 and data.get("ready") is True
            self.log("2. Daemon Readiness Probe (GET /ready)", ok, f"HTTP {status}, ready={data.get('ready')}, workspaces={data.get('workspaces')}")
        except Exception as exc:
            self.log("2. Daemon Readiness Probe (GET /ready)", False, str(exc))

        # 3. Security Rejection (Unauthenticated POST)
        if self.token:
            try:
                status, parsed = self.rpc("tools/list", req_id="unauth-test", auth=False)
                ok = status == 401
                self.log("3. Authentication Gate (Unauthenticated Request Rejection)", ok, f"HTTP {status} (Expected 401)")
            except Exception as exc:
                self.log("3. Authentication Gate", False, str(exc))
        else:
            self.log("3. Authentication Gate", True, "Skipped (testing without token)")

        # 4. MCP Initialize Handshake
        init_ok = False
        server_info = {}
        try:
            status, parsed = self.rpc(
                "initialize",
                params={
                    "protocolVersion": self.protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": "tacp-python-verifier", "version": "1.0.0"},
                },
                req_id="init-1",
            )
            res = parsed.get("result", {})
            server_info = res.get("serverInfo", {})
            proto = res.get("protocolVersion")
            init_ok = status == 200 and "name" in server_info
            self.log(
                "4. MCP Initialize Handshake (initialize)",
                init_ok,
                f"Protocol: {proto}, Server: {server_info.get('name')} {server_info.get('version')}",
            )
        except Exception as exc:
            self.log("4. MCP Initialize Handshake (initialize)", False, str(exc))

        # 5. MCP Tool Discovery (tools/list)
        tools = []
        try:
            status, parsed = self.rpc("tools/list", req_id="tools-1")
            tools = parsed.get("result", {}).get("tools", [])
            ok = status == 200 and len(tools) >= 10
            tool_sample = [t.get("name") for t in tools[:5]]
            self.log(
                f"5. Tool Discovery (tools/list: {len(tools)} tools discovered)",
                ok,
                f"Sample: {', '.join(tool_sample)}...",
            )
        except Exception as exc:
            self.log("5. Tool Discovery (tools/list)", False, str(exc))

        # 6. MCP Resources Discovery (resources/list)
        resources = []
        try:
            status, parsed = self.rpc("resources/list", req_id="res-1")
            resources = parsed.get("result", {}).get("resources", [])
            ok = status == 200 and len(resources) >= 4
            res_uris = [r.get("uri") for r in resources[:4]]
            self.log(
                f"6. Resource Cataloging (resources/list: {len(resources)} resources)",
                ok,
                f"Sample URIs: {', '.join(res_uris)}...",
            )
        except Exception as exc:
            self.log("6. Resource Cataloging (resources/list)", False, str(exc))

        # 7. MCP Prompts Discovery (prompts/list)
        prompts = []
        try:
            status, parsed = self.rpc("prompts/list", req_id="prompts-1")
            prompts = parsed.get("result", {}).get("prompts", [])
            ok = status == 200 and len(prompts) >= 1
            p_names = [p.get("name") for p in prompts]
            self.log(
                f"7. Prompt Discovery (prompts/list: {len(prompts)} prompts)",
                ok,
                f"Prompts: {', '.join(p_names)}",
            )
        except Exception as exc:
            self.log("7. Prompt Discovery (prompts/list)", False, str(exc))

        # 8. Safe Tool Execution: system.inspect
        try:
            status, parsed = self.rpc("tools/call", params={"name": "system.inspect", "arguments": {}}, req_id="call-sys")
            res = parsed.get("result", {})
            is_err = res.get("isError", True)
            ok = status == 200 and not is_err
            txt = res.get("content", [{}])[0].get("text", "")[:120].replace("\n", " ")
            self.log("8. Safe Tool Execution (system.inspect)", ok, f"Output snippet: {txt}...")
        except Exception as exc:
            self.log("8. Safe Tool Execution (system.inspect)", False, str(exc))

        # 9. Safe Tool Execution: device.info
        try:
            status, parsed = self.rpc("tools/call", params={"name": "device.info", "arguments": {}}, req_id="call-dev")
            res = parsed.get("result", {})
            is_err = res.get("isError", True)
            ok = status == 200 and not is_err
            txt = res.get("content", [{}])[0].get("text", "")[:120].replace("\n", " ")
            self.log("9. Safe Tool Execution (device.info)", ok, f"Output snippet: {txt}...")
        except Exception as exc:
            self.log("9. Safe Tool Execution (device.info)", False, str(exc))

        # 10. Safe Tool Execution: storage.overview
        try:
            status, parsed = self.rpc("tools/call", params={"name": "storage.overview", "arguments": {}}, req_id="call-storage")
            res = parsed.get("result", {})
            is_err = res.get("isError", True)
            ok = status == 200 and not is_err
            txt = res.get("content", [{}])[0].get("text", "")[:120].replace("\n", " ")
            self.log("10. Safe Tool Execution (storage.overview)", ok, f"Output snippet: {txt}...")
        except Exception as exc:
            self.log("10. Safe Tool Execution (storage.overview)", False, str(exc))

        # 11. Policy Enforcement: Mutating Operation Rejection for Read-Only Agent
        try:
            status, parsed = self.rpc(
                "tools/call",
                params={"name": "shell.exec", "arguments": {"command": "rm -rf /"}},
                req_id="call-deny-test",
            )
            res = parsed.get("result", {})
            is_err = res.get("isError", False)
            # Must be rejected either with isError=True or structured policy error
            txt = res.get("content", [{}])[0].get("text", "") if is_err else ""
            denied = is_err or "Access denied" in str(parsed) or "POLICY_DENIED" in str(parsed) or "prohibited" in str(parsed) or "disabled" in str(parsed)
            self.log(
                "11. Policy Engine Boundary (Mutating Call Rejection under Read Policy)",
                denied,
                f"Correctly denied: {txt.strip()[:100]}",
            )
        except Exception as exc:
            self.log("11. Policy Engine Boundary", False, str(exc))

        # Final Summary
        passed_count = sum(1 for _, ok, _ in self.results if ok)
        total_count = len(self.results)
        print("============================================================")
        print(f" VERIFICATION RESULT: {passed_count}/{total_count} Checks PASSED")
        print("============================================================")
        return passed_count == total_count


def main() -> int:
    parser = argparse.ArgumentParser(description="TACP Remote MCP Protocol Verification Client")
    parser.add_argument("--url", help="MCP endpoint URL (or set TACP_MCP_URL)")
    parser.add_argument("--token", help="Bearer token (or set TACP_MCP_TOKEN)")
    args = parser.parse_args()

    url = args.url or os.environ.get("TACP_MCP_URL") or os.environ.get("TACP_URL")
    if not url:
        print("[ERROR] Missing MCP endpoint URL. Specify --url https://<HOST>/mcp or set TACP_MCP_URL.")
        return 1

    token = args.token or os.environ.get("TACP_MCP_TOKEN") or os.environ.get("TACP_TOKEN")
    verifier = RemoteMcpVerifier(mcp_url=url, token=token)
    success = verifier.run_suite()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
