"""Direct Network / LAN / Tailscale Provider for TACP."""

from __future__ import annotations

import socket
from typing import Any, Optional

from tacp.remote.tunnel_providers.base import BaseTunnelProvider, TunnelInfo


def get_local_ip() -> str:
    """Attempt to discover the primary local IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Does not send packets, resolves routing interface
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


class DirectTunnelProvider(BaseTunnelProvider):
    """Direct provider exposing server on LAN, Tailscale, or custom domain."""

    def __init__(self) -> None:
        self._local_port: Optional[int] = None
        self._custom_host: Optional[str] = None
        self._is_active: bool = False

    @property
    def name(self) -> str:
        return "direct"

    def start(self, local_port: int, **kwargs: Any) -> TunnelInfo:
        self._local_port = local_port
        custom_domain = kwargs.get("custom_domain") or kwargs.get("host")
        if custom_domain:
            self._custom_host = custom_domain
            scheme = "https" if kwargs.get("https", False) else "http"
            public_url = f"{scheme}://{custom_domain}:{local_port}" if ":" not in custom_domain else f"{scheme}://{custom_domain}"
        else:
            local_ip = get_local_ip()
            self._custom_host = local_ip
            public_url = f"http://{local_ip}:{local_port}"

        self._is_active = True
        return TunnelInfo(
            provider_name=self.name,
            public_url=public_url,
            mcp_endpoint=f"{public_url}/mcp",
            is_active=True,
            status_message="Direct network endpoint active",
            details={"host": self._custom_host, "port": local_port},
        )

    def stop(self) -> bool:
        self._is_active = False
        self._custom_host = None
        return True

    def get_status(self) -> TunnelInfo:
        if not self._is_active or not self._local_port:
            return TunnelInfo(
                provider_name=self.name,
                public_url="",
                mcp_endpoint="",
                is_active=False,
                status_message="Stopped",
                details={},
            )
        ip = self._custom_host or get_local_ip()
        url = f"http://{ip}:{self._local_port}"
        return TunnelInfo(
            provider_name=self.name,
            public_url=url,
            mcp_endpoint=f"{url}/mcp",
            is_active=True,
            status_message="Active",
            details={"host": ip, "port": self._local_port},
        )
