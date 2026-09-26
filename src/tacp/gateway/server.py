"""Standalone Self-Hostable TACP Remote MCP Gateway.

Enables any MCP client on the public internet to reach Android TACP devices
through an outbound authenticated relay channel.
Can be deployed on any VPS, cloud server, or Docker container with TLS.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class PendingClientRequest:
    request_id: str
    device_id: str
    payload: Dict[str, Any]
    response_event: threading.Event
    response_payload: Optional[Dict[str, Any]] = None
    created_at: float = 0.0




class GatewayState:
    """Manages active devices, pending requests, and authentication."""

    def __init__(self, admin_token: Optional[str] = None) -> None:
        self.admin_token = admin_token or f"tacp_adm_{uuid.uuid4().hex}"
        self.devices: Dict[str, Dict[str, Any]] = {}
        self.device_locks: Dict[str, threading.Lock] = {}
        self.pending_requests: Dict[str, PendingClientRequest] = {}
        self.device_request_queues: Dict[str, list[PendingClientRequest]] = {}
        self.device_poll_events: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def register_device(self, device_id: str, device_name: str, device_secret: str) -> bool:
        with self._lock:
            if device_id in self.devices:
                # verify secret
                if self.devices[device_id].get("secret") != device_secret:
                    return False
            self.devices[device_id] = {
                "id": device_id,
                "name": device_name,
                "secret": device_secret,
                "last_seen": time.time(),
                "connected": True,
            }
            if device_id not in self.device_request_queues:
                self.device_request_queues[device_id] = []
            if device_id not in self.device_poll_events:
                self.device_poll_events[device_id] = threading.Event()
            return True

    def queue_request_for_device(
        self, device_id: str, payload: Dict[str, Any], timeout: float = 30.0
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            if device_id not in self.devices or not self.devices[device_id].get("connected"):
                return None
            req_id = f"greq_{uuid.uuid4().hex[:12]}"
            event = threading.Event()
            p_req = PendingClientRequest(
                request_id=req_id,
                device_id=device_id,
                payload=payload,
                response_event=event,
                created_at=time.time(),
            )
            self.pending_requests[req_id] = p_req
            self.device_request_queues[device_id].append(p_req)
            poll_event = self.device_poll_events[device_id]
            poll_event.set()

        # Wait for device to respond
        finished = event.wait(timeout=timeout)
        with self._lock:
            self.pending_requests.pop(req_id, None)
            if finished and p_req.response_payload is not None:
                return p_req.response_payload
            return None

    def poll_for_device(self, device_id: str, device_secret: str, wait_timeout: float = 25.0) -> Optional[PendingClientRequest]:
        with self._lock:
            dev = self.devices.get(device_id)
            if not dev or dev.get("secret") != device_secret:
                return None
            dev["last_seen"] = time.time()
            dev["connected"] = True
            queue = self.device_request_queues.get(device_id, [])
            if queue:
                return queue.pop(0)
            event = self.device_poll_events[device_id]
            event.clear()

        event.wait(timeout=wait_timeout)
        with self._lock:
            queue = self.device_request_queues.get(device_id, [])
            if queue:
                return queue.pop(0)
            return None

    def submit_device_response(self, request_id: str, response_payload: Dict[str, Any]) -> bool:
        with self._lock:
            p_req = self.pending_requests.get(request_id)
            if not p_req:
                return False
            p_req.response_payload = response_payload
            p_req.response_event.set()
            return True


class GatewayHttpHandler(BaseHTTPRequestHandler):
    """HTTP Handler for Gateway routing MCP and device relay traffic."""

    server: GatewayServer

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Mcp-Session-Id")

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path in ("/health", "/healthz"):
            body = json.dumps({"status": "ok", "service": "tacp-gateway"}).encode("utf-8")
            self.send_response(200)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/ready":
            with self.server.state._lock:
                dev_count = len(self.server.state.devices)
            body = json.dumps({"ready": True, "registered_devices": dev_count}).encode("utf-8")
            self.send_response(200)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # MCP Metadata
        if path.endswith("/mcp") or path == "/":
            body = json.dumps({
                "name": "tacp-gateway",
                "version": "1.0.0",
                "protocolVersion": "2026-07-28",
                "transport": "streamable-http",
                "description": "TACP Universal Remote MCP Gateway",
            }).encode("utf-8")
            self.send_response(200)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length > 0 else b""
        raw_body = body_bytes.decode("utf-8") if body_bytes else "{}"

        try:
            data = json.loads(raw_body)
        except Exception:
            data = {}

        # 1. Device Relay Handshake: POST /relay/register
        if path == "/relay/register":
            dev_id = data.get("device_id")
            dev_name = data.get("device_name", "Android-Device")
            dev_secret = data.get("device_secret")
            if not dev_id or not dev_secret:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error":"Missing device_id or device_secret"}\n')
                return
            ok = self.server.state.register_device(dev_id, dev_name, dev_secret)
            if ok:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"status": "registered", "device_id": dev_id}).encode("utf-8"))
            else:
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b'{"error":"Invalid device credentials"}\n')
            return

        # 2. Device Long-poll Channel: POST /relay/poll
        if path == "/relay/poll":
            dev_id = data.get("device_id")
            dev_secret = data.get("device_secret")
            if not dev_id or not dev_secret:
                self.send_response(401)
                self.end_headers()
                return
            req = self.server.state.poll_for_device(dev_id, dev_secret, wait_timeout=20.0)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if req:
                self.wfile.write(json.dumps({
                    "has_request": True,
                    "request_id": req.request_id,
                    "payload": req.payload,
                }).encode("utf-8"))
            else:
                self.wfile.write(b'{"has_request":false}\n')
            return

        # 3. Device Response Channel: POST /relay/response
        if path == "/relay/response":
            req_id = data.get("request_id")
            resp_payload = data.get("payload")
            if not req_id or resp_payload is None:
                self.send_response(400)
                self.end_headers()
                return
            ok = self.server.state.submit_device_response(req_id, resp_payload)
            self.send_response(200 if ok else 404)
            self.end_headers()
            self.wfile.write(b'{"status":"received"}\n' if ok else b'{"error":"unknown_or_expired_request"}\n')
            return

        # 4. Public MCP Client Inbound: POST /mcp or POST /device/<device_id>/mcp
        if path == "/mcp" or path.startswith("/device/"):
            # Resolve target device
            target_device = None
            if path.startswith("/device/"):
                parts = path.split("/")
                if len(parts) >= 4 and parts[3] == "mcp":
                    target_device = parts[2]
            if not target_device:
                # Default to only registered device if exactly one exists
                with self.server.state._lock:
                    if len(self.server.state.devices) == 1:
                        target_device = list(self.server.state.devices.keys())[0]

            if not target_device:
                err = json.dumps({
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "error": {"code": -32002, "message": "No active Android device available or device_id unspecified"}
                }).encode("utf-8")
                self.send_response(503)
                self._cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err)
                return

            # Forward client's auth header if present
            forward_payload = {
                "jsonrpc_payload": data,
                "headers": {
                    "Authorization": self.headers.get("Authorization", ""),
                    "Mcp-Session-Id": self.headers.get("Mcp-Session-Id", ""),
                }
            }

            resp = self.server.state.queue_request_for_device(target_device, forward_payload, timeout=30.0)
            if resp is None:
                err = json.dumps({
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "error": {"code": -32000, "message": "Device timeout: Android TACP agent did not respond within 30s"}
                }).encode("utf-8")
                self.send_response(504)
                self._cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(err)
                return

            resp_bytes = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self._cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_bytes)))
            self.end_headers()
            self.wfile.write(resp_bytes)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(f"[Gateway] {format % args}\n")


class GatewayServer(ThreadingHTTPServer):
    """Threading HTTP server for TACP Gateway."""

    def __init__(self, server_address: tuple[str, int], state: GatewayState) -> None:
        super().__init__(server_address, GatewayHttpHandler)
        self.state = state
        self.daemon_threads = True


def main() -> int:
    parser = argparse.ArgumentParser(description="TACP Universal Remote MCP Gateway")
    parser.add_argument("--host", default="0.0.0.0", help="Listen host")
    parser.add_argument("--port", type=int, default=9090, help="Listen port")
    args = parser.parse_args()

    state = GatewayState()
    server = GatewayServer((args.host, args.port), state)
    sys.stderr.write(f"[INFO] TACP Gateway running at http://{args.host}:{args.port}\n")
    sys.stderr.write(f"[INFO] MCP endpoint: http://{args.host}:{args.port}/mcp\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
