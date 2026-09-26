"""Optional OpenAI Tunnel Adapter for TACP.

Provides backward-compatible integration with OpenAI's tunnel-client daemon.
This vendor adapter is optional and isolated from the core universal MCP engine.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from tacp.remote.tunnel_providers.base import BaseTunnelProvider, TunnelInfo

logger = logging.getLogger(__name__)


class OpenAiTunnelAdapter(BaseTunnelProvider):
    """Manages OpenAI's proprietary tunnel-client daemon."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = data_dir or (Path.home() / ".tacp")
        self.profile_path = Path.home() / ".config" / "tunnel-client" / "tacp-http.yaml"
        self._process: Optional[subprocess.Popen[str]] = None

    @property
    def name(self) -> str:
        return "openai"

    def is_available(self) -> bool:
        return bool(shutil.which("tunnel-client"))

    def start(self, local_port: int, **kwargs: Any) -> TunnelInfo:
        if not self.is_available():
            return TunnelInfo(
                provider_name=self.name,
                public_url="",
                mcp_endpoint="",
                is_active=False,
                status_message="tunnel-client not found in PATH.",
                details={"available": False},
            )

        cmd = ["tunnel-client", "run", "--profile", "tacp-http"]
        try:
            self._process = subprocess.Popen(cmd)
            return TunnelInfo(
                provider_name=self.name,
                public_url="https://platform.openai.com/settings/organization/tunnels",
                mcp_endpoint="https://chatgpt.com/#settings/Connectors",
                is_active=True,
                status_message="OpenAI tunnel-client running in background",
                details={"pid": self._process.pid},
            )
        except Exception as exc:
            return TunnelInfo(
                provider_name=self.name,
                public_url="",
                mcp_endpoint="",
                is_active=False,
                status_message=f"Failed to start tunnel-client: {exc}",
                details={"error": str(exc)},
            )

    def stop(self) -> bool:
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        self._process = None
        return True

    def get_status(self) -> TunnelInfo:
        active = bool(self._process and self._process.poll() is None)
        return TunnelInfo(
            provider_name=self.name,
            public_url="https://platform.openai.com/settings/organization/tunnels"
            if active
            else "",
            mcp_endpoint="https://chatgpt.com/#settings/Connectors" if active else "",
            is_active=active,
            status_message="Active" if active else "Stopped",
            details={},
        )
