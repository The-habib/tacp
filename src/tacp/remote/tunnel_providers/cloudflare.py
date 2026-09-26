"""Cloudflare Quick Tunnel Provider for TACP.

Provides instant, zero-configuration public HTTPS endpoints via Cloudflare Quick Tunnels.
No Cloudflare account, domain, or router port-forwarding required.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from tacp.remote.tunnel_providers.base import BaseTunnelProvider, TunnelInfo

logger = logging.getLogger(__name__)

URL_REGEX = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


class CloudflareTunnelProvider(BaseTunnelProvider):
    """Manages Cloudflare Quick Tunnel daemon."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = data_dir or (Path.home() / ".tacp")
        self.log_file = self.data_dir / "cloudflared.log"
        self.pid_file = self.data_dir / "cloudflared.pid"
        self._process: Optional[subprocess.Popen[str]] = None
        self._public_url: Optional[str] = None
        self._local_port: Optional[int] = None

    @property
    def name(self) -> str:
        return "cloudflare"

    def _find_binary(self) -> Optional[str]:
        # 1. System PATH
        bin_path = shutil.which("cloudflared")
        if bin_path:
            return bin_path

        # 2. Termux usr/bin
        termux_bin = Path("/data/data/com.termux/files/usr/bin/cloudflared")
        if termux_bin.exists() and os.access(termux_bin, os.X_OK):
            return str(termux_bin)

        # 3. Check ~/.tacp/bin/cloudflared
        custom_bin = self.data_dir / "bin" / "cloudflared"
        if custom_bin.exists() and os.access(custom_bin, os.X_OK):
            return str(custom_bin)

        return None

    def start(self, local_port: int, **kwargs: Any) -> TunnelInfo:
        self._local_port = local_port
        bin_path = self._find_binary()
        if not bin_path:
            return TunnelInfo(
                provider_name=self.name,
                public_url="",
                mcp_endpoint="",
                is_active=False,
                status_message="cloudflared executable not found. Install via 'pkg install cloudflared'.",
                details={"installed": False},
            )

        self.data_dir.mkdir(parents=True, exist_ok=True)
        # Launch cloudflared
        cmd = [
            bin_path,
            "tunnel",
            "--url",
            f"http://127.0.0.1:{local_port}",
            "--no-autoupdate",
            "--edge-ip-version",
            "4",
        ]

        with open(self.log_file, "w", encoding="utf-8") as out:
            self._process = subprocess.Popen(
                cmd,
                stdout=out,
                stderr=out,
                text=True,
                start_new_session=True,
            )
        if self._process:
            self.pid_file.write_text(str(self._process.pid), encoding="utf-8")

        # Wait up to 25 seconds to discover assigned public URL
        start_wait = time.time()
        discovered_url = None
        while time.time() - start_wait < 25.0:
            if self._process.poll() is not None:
                break
            if self.log_file.exists():
                with open(self.log_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    matches = URL_REGEX.findall(content)
                    if matches:
                        discovered_url = matches[0]
                        break
            time.sleep(0.5)

        if not discovered_url:
            self.stop()
            return TunnelInfo(
                provider_name=self.name,
                public_url="",
                mcp_endpoint="",
                is_active=False,
                status_message="Failed to establish Cloudflare tunnel within 25 seconds. Check cloudflared.log",
                details={"log_file": str(self.log_file)},
            )

        self._public_url = discovered_url
        endpoint = f"{discovered_url}/mcp"

        return TunnelInfo(
            provider_name=self.name,
            public_url=discovered_url,
            mcp_endpoint=endpoint,
            is_active=True,
            status_message="Cloudflare Quick Tunnel established successfully",
            details={
                "pid": self._process.pid if self._process else None,
                "local_port": local_port,
                "log_file": str(self.log_file),
            },
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
        elif self.pid_file.exists():
            try:
                pid = int(self.pid_file.read_text(encoding="utf-8").strip())
                os.kill(pid, 15)
            except Exception:
                pass

        if self.pid_file.exists():
            try:
                self.pid_file.unlink()
            except Exception:
                pass

        self._process = None
        self._public_url = None
        return True

    def get_status(self) -> TunnelInfo:
        running_pid = None
        if self._process and self._process.poll() is None:
            running_pid = self._process.pid
        elif self.pid_file.exists():
            try:
                pid = int(self.pid_file.read_text(encoding="utf-8").strip())
                os.kill(pid, 0)
                running_pid = pid
            except Exception:
                try:
                    self.pid_file.unlink()
                except Exception:
                    pass

        url = self._public_url
        if running_pid and not url and self.log_file.exists():
            try:
                content = self.log_file.read_text(encoding="utf-8", errors="ignore")
                matches = URL_REGEX.findall(content)
                if matches:
                    url = matches[0]
                    self._public_url = url
            except Exception:
                pass

        is_active = bool(running_pid and url)
        return TunnelInfo(
            provider_name=self.name,
            public_url=url or "",
            mcp_endpoint=f"{url}/mcp" if url else "",
            is_active=is_active,
            status_message="Active" if is_active else "Stopped",
            details={"pid": running_pid},
        )
