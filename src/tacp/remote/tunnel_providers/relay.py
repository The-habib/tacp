"""TACP Gateway Relay Client.

Establishes an outbound, authenticated, long-poll or WebSocket session from
the Android Termux device to a self-hosted or managed TACP Gateway.
Transverses carrier NAT and dynamic IPs with automatic reconnection.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from tacp.access.mcp.server import McpServer
    from tacp.control.auth import TokenService
    from tacp.control.pairing import DeviceIdentity

from tacp.access.mcp.protocol import McpRequest
from tacp.remote.tunnel_providers.base import BaseTunnelProvider, TunnelInfo

logger = logging.getLogger(__name__)


class RelayTunnelProvider(BaseTunnelProvider):
    """Outbound relay provider connecting Android TACP to a TACP Gateway."""

    def __init__(
        self,
        mcp_server: McpServer,
        identity: DeviceIdentity,
        gateway_url: str,
        token_service: Optional[TokenService] = None,
    ) -> None:
        self.mcp_server = mcp_server
        self.identity = identity
        self.gateway_url = gateway_url.rstrip("/")
        self.token_service = token_service
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._status_msg = "Initialized"

    @property
    def name(self) -> str:
        return "relay"

    def start(self, local_port: int = 0, **kwargs: Any) -> TunnelInfo:
        """Register with the gateway and start the outbound worker loop."""
        if self._running:
            return self.get_status()

        # 1. Register with gateway
        reg_url = f"{self.gateway_url}/relay/register"
        reg_payload = json.dumps(
            {
                "device_id": self.identity.device_id,
                "device_name": self.identity.device_name,
                "device_secret": self.identity.device_secret,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            reg_url,
            data=reg_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Gateway returned status {resp.status}")
        except Exception as exc:
            self._status_msg = f"Failed to register with gateway: {exc}"
            return TunnelInfo(
                provider_name=self.name,
                public_url="",
                mcp_endpoint="",
                is_active=False,
                status_message=self._status_msg,
                details={"gateway_url": self.gateway_url, "error": str(exc)},
            )

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        self._status_msg = "Connected and polling"

        endpoint = f"{self.gateway_url}/device/{self.identity.device_id}/mcp"
        return TunnelInfo(
            provider_name=self.name,
            public_url=self.gateway_url,
            mcp_endpoint=endpoint,
            is_active=True,
            status_message=self._status_msg,
            details={
                "gateway_url": self.gateway_url,
                "device_id": self.identity.device_id,
            },
        )

    def _poll_loop(self) -> None:
        """Continuously long-poll the gateway for incoming MCP requests."""
        poll_url = f"{self.gateway_url}/relay/poll"
        resp_url = f"{self.gateway_url}/relay/response"
        backoff = 1.0

        while self._running:
            try:
                poll_payload = json.dumps(
                    {
                        "device_id": self.identity.device_id,
                        "device_secret": self.identity.device_secret,
                    }
                ).encode("utf-8")

                req = urllib.request.Request(
                    poll_url,
                    data=poll_payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )

                with urllib.request.urlopen(req, timeout=35.0) as resp:
                    if resp.status == 200:
                        backoff = 1.0
                        data = json.loads(resp.read().decode("utf-8"))
                        if data.get("has_request"):
                            self._handle_dispatched_request(
                                resp_url, data["request_id"], data["payload"]
                            )

            except Exception:
                if not self._running:
                    break
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 10.0)

    def _handle_dispatched_request(
        self, resp_url: str, request_id: str, payload_info: Dict[str, Any]
    ) -> None:
        """Process incoming MCP request and post result back to gateway."""
        jsonrpc = payload_info.get("jsonrpc_payload", {})
        headers = payload_info.get("headers", {})

        # Authenticate token if present
        auth_header = headers.get("Authorization", "")
        principal = None
        if auth_header and self.token_service:
            token_str = auth_header.replace("Bearer ", "").strip()
            token_rec = self.token_service.validate_token(token_str)
            if token_rec:
                principal = self.token_service.principal_from_token(token_rec)

        try:
            req_obj = McpRequest.from_dict(jsonrpc)
            if req_obj.method == "tools/call" and principal is not None:
                tool_name = req_obj.params.get("name")
                args = req_obj.params.get("arguments", {})
                tool_res = self.mcp_server.tool_registry.execute_tool(
                    tool_name, args, principal=principal, request_id=request_id
                )
                response_payload = {
                    "jsonrpc": "2.0",
                    "id": req_obj.id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(tool_res, indent=2)}],
                        "isError": False,
                        "resultType": "complete",
                    },
                }
            else:
                resp = self.mcp_server.handle_request(req_obj)
                response_payload = resp.to_dict() if resp else {"jsonrpc": "2.0", "result": None}
        except Exception as exc:
            response_payload = {
                "jsonrpc": "2.0",
                "id": jsonrpc.get("id"),
                "error": {"code": -32603, "message": str(exc)},
            }

        # Send response to gateway
        try:
            submit_data = json.dumps(
                {
                    "request_id": request_id,
                    "payload": response_payload,
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                resp_url,
                data=submit_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10.0):
                pass
        except Exception as exc:
            sys.stderr.write(f"[Relay] Failed to submit response for {request_id}: {exc}\n")

    def stop(self) -> bool:
        self._running = False
        self._status_msg = "Stopped"
        return True

    def get_status(self) -> TunnelInfo:
        endpoint = (
            f"{self.gateway_url}/device/{self.identity.device_id}/mcp" if self._running else ""
        )
        return TunnelInfo(
            provider_name=self.name,
            public_url=self.gateway_url if self._running else "",
            mcp_endpoint=endpoint,
            is_active=self._running,
            status_message=self._status_msg,
            details={
                "gateway_url": self.gateway_url,
                "device_id": self.identity.device_id,
                "running": self._running,
            },
        )
