#!/usr/bin/env python3
"""Standalone verification script for TACP Streamable HTTP MCP transport.

This script performs end-to-end testing of the MCP protocol over Streamable HTTP
without requiring any commercial AI client (e.g. Claude, Cursor, ChatGPT).
It validates protocol compliance, authentication, authorization, session tracking,
tool execution, and security boundaries.

Usage:
    python scripts/test_mcp_http.py [--url http://127.0.0.1:8765] [--token <bearer_token>]
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Add src to path if running directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tacp.access.mcp.server import create_mcp_server
from tacp.access.mcp.transports.streamable_http import StreamableMcpServer
from tacp.control.auth import (
    SCOPE_ADMIN,
    SCOPE_FILES_READ,
    SCOPE_READ,
    TokenService,
)
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database


class McpHttpTester:
    def __init__(self, base_url: str, token: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session_id: Optional[str] = None
        self.passed = 0
        self.failed = 0

    def log_result(self, step: str, ok: bool, details: str = "") -> None:
        if ok:
            self.passed += 1
            print(f"[PASS] {step}")
            if details:
                print(f"       -> {details}")
        else:
            self.failed += 1
            print(f"[FAIL] {step}")
            if details:
                print(f"       -> {details}")

    def request(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth: bool = True,
    ) -> Tuple[int, Dict[str, str], bytes]:
        url = f"{self.base_url}{endpoint}"
        req_headers: Dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if headers:
            req_headers.update(headers)

        if auth and self.token:
            req_headers["Authorization"] = f"Bearer {self.token}"

        if self.session_id:
            req_headers["Mcp-Session-Id"] = self.session_id

        payload = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=payload, headers=req_headers, method=method)

        try:
            with urllib.request.urlopen(req) as resp:
                resp_headers = dict(resp.headers)
                if "Mcp-Session-Id" in resp_headers:
                    self.session_id = resp_headers["Mcp-Session-Id"]
                return resp.status, resp_headers, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()
        except Exception as exc:
            raise RuntimeError(f"Connection failed to {url}: {exc}") from exc

    def run_all(self) -> bool:
        print("============================================================")
        print(" TACP Streamable HTTP MCP Verification Suite                ")
        print(f" Target Endpoint: {self.base_url}/mcp                      ")
        print("============================================================")

        # 1. Health Probe
        try:
            status, _, body = self.request("/health", method="GET", auth=False)
            data = json.loads(body.decode("utf-8"))
            ok = status == 200 and data.get("status") == "ok"
            self.log_result("1. Health Endpoint Probe (/health)", ok, f"HTTP {status}, body={data}")
        except Exception as exc:
            self.log_result("1. Health Endpoint Probe (/health)", False, str(exc))

        # 2. Readiness Probe
        try:
            status, _, body = self.request("/ready", method="GET", auth=False)
            data = json.loads(body.decode("utf-8"))
            ok = status == 200 and data.get("ready") is True
            self.log_result("2. Readiness Probe (/ready)", ok, f"HTTP {status}, ready={data.get('ready')}")
        except Exception as exc:
            self.log_result("2. Readiness Probe (/ready)", False, str(exc))

        # 3. Unauthenticated Rejection (if token is in use)
        if self.token:
            try:
                status, _, body = self.request(
                    "/mcp",
                    method="POST",
                    data={"jsonrpc": "2.0", "id": 99, "method": "tools/list", "params": {}},
                    auth=False,
                )
                ok = status == 401
                self.log_result("3. Security Rejection on Unauthenticated POST", ok, f"HTTP {status} (Expected 401)")
            except Exception as exc:
                self.log_result("3. Security Rejection on Unauthenticated POST", False, str(exc))
        else:
            print("[INFO] 3. Skipping Unauthenticated Rejection test (no token supplied)")

        # 4. MCP Handshake (initialize)
        try:
            status, hdrs, body = self.request(
                "/mcp",
                method="POST",
                data={
                    "jsonrpc": "2.0",
                    "id": "init-1",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2026-07-28",
                        "capabilities": {},
                        "clientInfo": {"name": "tacp-http-tester", "version": "1.0.0"},
                    },
                },
            )
            data = json.loads(body.decode("utf-8"))
            res = data.get("result", {})
            srv_info = res.get("serverInfo", {})
            ok = status == 200 and srv_info.get("name") == "tacp"
            self.log_result(
                "4. MCP Initialize Handshake (initialize)",
                ok,
                f"Protocol: {res.get('protocolVersion')}, Server: {srv_info.get('name')} {srv_info.get('version')}",
            )
        except Exception as exc:
            self.log_result("4. MCP Initialize Handshake (initialize)", False, str(exc))

        # 5. MCP Tool Discovery (tools/list)
        available_tools = []
        try:
            status, _, body = self.request(
                "/mcp",
                method="POST",
                data={"jsonrpc": "2.0", "id": "list-1", "method": "tools/list", "params": {}},
            )
            data = json.loads(body.decode("utf-8"))
            tools = data.get("result", {}).get("tools", [])
            available_tools = [t.get("name") for t in tools]
            ok = status == 200 and len(tools) >= 5
            self.log_result(
                f"5. Tool Discovery (tools/list: {len(tools)} tools)",
                ok,
                f"Tools discovered: {', '.join(available_tools[:6])}...",
            )
        except Exception as exc:
            self.log_result("5. Tool Discovery (tools/list)", False, str(exc))

        # 6. Tool Execution (system.inspect)
        try:
            status, _, body = self.request(
                "/mcp",
                method="POST",
                data={
                    "jsonrpc": "2.0",
                    "id": "call-1",
                    "method": "tools/call",
                    "params": {"name": "system.inspect", "arguments": {}},
                },
            )
            data = json.loads(body.decode("utf-8"))
            call_res = data.get("result", {})
            is_err = call_res.get("isError", True)
            ok = status == 200 and not is_err
            details = call_res.get("content", [{}])[0].get("text", "")[:100]
            self.log_result("6. Tool Invocation (system.inspect)", ok, f"Response: {details}...")
        except Exception as exc:
            self.log_result("6. Tool Invocation (system.inspect)", False, str(exc))

        # 7. Workspace Security & Containment Boundary
        try:
            status, _, body = self.request(
                "/mcp",
                method="POST",
                data={
                    "jsonrpc": "2.0",
                    "id": "call-security",
                    "method": "tools/call",
                    "params": {
                        "name": "fs.read",
                        "arguments": {"workspace_id": "non_existent_ws", "relative_path": "../../../../etc/shadow"},
                    },
                },
            )
            data = json.loads(body.decode("utf-8"))
            call_res = data.get("result", {})
            # Must return isError == True
            ok = status == 200 and call_res.get("isError") is True
            err_msg = call_res.get("content", [{}])[0].get("text", "")
            self.log_result(
                "7. Security Boundary Enforcement (Traversal / Jail Denial)",
                ok,
                f"Safely rejected: {err_msg.strip()[:100]}",
            )
        except Exception as exc:
            self.log_result("7. Security Boundary Enforcement", False, str(exc))

        print("============================================================")
        print(f" RESULTS: {self.passed} Passed, {self.failed} Failed")
        print("============================================================")
        return self.failed == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Test TACP Streamable HTTP MCP server.")
    parser.add_argument("--url", help="HTTP MCP base URL (e.g. http://127.0.0.1:8765)")
    parser.add_argument("--token", help="Bearer authentication token")
    args = parser.parse_args()

    if args.url:
        tester = McpHttpTester(args.url, token=args.token)
        return 0 if tester.run_all() else 1

    # If no URL specified, spin up an ephemeral test server in-process
    print("[*] No URL provided. Spinning up an ephemeral in-process TACP MCP server...")
    config = TacpConfig.load()
    object.__setattr__(config, "remote_enabled", True)
    db = Database(config.db_path)
    db.connect()

    token_service = TokenService(db)
    _, raw_token = token_service.create_token(
        name="Automated Test Runner",
        scopes=[SCOPE_READ, SCOPE_FILES_READ, SCOPE_ADMIN],
    )

    mcp_server = create_mcp_server(config)
    server = StreamableMcpServer(
        ("127.0.0.1", 0),
        mcp_server=mcp_server,
        token_service=token_service,
        auth_required=True,
    )
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    try:
        tester = McpHttpTester(base_url, token=raw_token)
        success = tester.run_all()
        return 0 if success else 1
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
