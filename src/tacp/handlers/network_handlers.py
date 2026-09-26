"""Handlers for network.* and wifi.* namespace capabilities."""

from __future__ import annotations

import json
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from tacp.backends.base import BaseBackend


def handle_network_interfaces(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """List network interfaces and active IP addresses."""
    interfaces: List[Dict[str, Any]] = []

    try:
        p = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=2.0)
        if p.returncode == 0:
            blocks = p.stdout.split("\n\n")
            for block in blocks:
                lines = block.strip().splitlines()
                if not lines:
                    continue
                first = lines[0].split()
                iface_name = first[0].rstrip(":")
                inet_match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", block)
                mask_match = re.search(r"netmask\s+(\d+\.\d+\.\d+\.\d+)", block)
                flags_match = re.search(r"flags=\d+<([^>]+)>", block)

                interfaces.append({
                    "name": iface_name,
                    "ip": inet_match.group(1) if inet_match else None,
                    "netmask": mask_match.group(1) if mask_match else None,
                    "flags": flags_match.group(1).split(",") if flags_match else [],
                })
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    return {"success": True, "count": len(interfaces), "interfaces": interfaces}


def handle_network_ping(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Ping remote host and measure round-trip latency."""
    host = params.get("host", "1.1.1.1")
    count = int(params.get("count", 3))

    try:
        p = subprocess.run(["ping", "-c", str(count), "-W", "2", host], capture_output=True, text=True, timeout=10.0)
        output = p.stdout

        # Parse packet loss
        loss_match = re.search(r"(\d+)%\s+packet loss", output)
        loss_percent = float(loss_match.group(1)) if loss_match else (0.0 if p.returncode == 0 else 100.0)

        # Parse rtt min/avg/max/mdev
        rtt_match = re.search(r"rtt\s+min/avg/max/mdev\s*=\s*([\d\.]+)/([\d\.]+)/([\d\.]+)/([\d\.]+)", output)
        avg_ms = float(rtt_match.group(2)) if rtt_match else None

        return {
            "success": p.returncode == 0,
            "host": host,
            "packet_loss_percent": loss_percent,
            "avg_latency_ms": avg_ms,
            "raw_summary": output.splitlines()[-2:] if output else [],
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def handle_network_resolve(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Perform DNS lookup for hostname."""
    host = params.get("host")
    if not host:
        return {"success": False, "error": "Missing required parameter 'host'"}

    try:
        addr_info = socket.getaddrinfo(host, None)
        ips = sorted(list(set(item[4][0] for item in addr_info)))
        return {"success": True, "host": host, "resolved_ips": ips}
    except Exception as exc:
        return {"success": False, "error": f"Resolution error: {exc}"}


def handle_network_http_request(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute structured HTTP request (GET, POST, PUT, DELETE)."""
    url = params.get("url")
    if not url:
        return {"success": False, "error": "Missing required parameter 'url'"}

    method = params.get("method", "GET").upper()
    headers = params.get("headers", {})
    body = params.get("body")
    timeout = float(params.get("timeout", 15.0))

    payload_bytes = None
    if body is not None:
        if isinstance(body, (dict, list)):
            payload_bytes = json.dumps(body).encode("utf-8")
            if "Content-Type" not in headers:
                headers["Content-Type"] = "application/json"
        else:
            payload_bytes = str(body).encode("utf-8")

    req = urllib.request.Request(url, data=payload_bytes, headers=headers, method=method)
    start_time = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_body = resp.read(256 * 1024).decode("utf-8", errors="replace")
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "success": True,
                "status_code": resp.status,
                "headers": dict(resp.headers),
                "duration_ms": duration_ms,
                "body": resp_body,
            }
    except urllib.error.HTTPError as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "success": False,
            "status_code": exc.code,
            "headers": dict(exc.headers),
            "duration_ms": duration_ms,
            "body": exc.read().decode("utf-8", errors="replace") if exc.fp else "",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def handle_network_download(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Download a file from remote URL to target local path."""
    url = params.get("url")
    destination = params.get("destination")
    if not url or not destination:
        return {"success": False, "error": "Missing required parameter 'url' or 'destination'"}

    dest_path = Path(destination).expanduser().resolve()
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    start_time = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=30.0) as resp, open(dest_path, "wb") as out:
            bytes_read = 0
            while chunk := resp.read(64 * 1024):
                out.write(chunk)
                bytes_read += len(chunk)

        duration_sec = round(time.perf_counter() - start_time, 2)
        return {
            "success": True,
            "url": url,
            "destination": str(dest_path),
            "bytes_downloaded": bytes_read,
            "duration_seconds": duration_sec,
        }
    except Exception as exc:
        return {"success": False, "error": f"Download failed: {exc}"}


def handle_network_diagnostics(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Run comprehensive device network connectivity and DNS diagnostic."""
    ifaces = handle_network_interfaces(backend, {})
    dns_res = handle_network_resolve(backend, {"host": "cloudflare.com"})
    ping_res = handle_network_ping(backend, {"host": "1.1.1.1", "count": 2})

    return {
        "success": True,
        "interfaces_count": ifaces.get("count", 0),
        "interfaces": ifaces.get("interfaces", []),
        "dns_resolution": dns_res.get("success", False),
        "resolved_ips": dns_res.get("resolved_ips", []),
        "ping_connectivity": ping_res.get("success", False),
        "avg_latency_ms": ping_res.get("avg_latency_ms"),
    }


def handle_wifi_status(backend: BaseBackend, params: Dict[str, Any]) -> Dict[str, Any]:
    """Query Wi-Fi status and connection parameters."""
    return {
        "success": True,
        "details": "Detailed Wi-Fi SSID and BSSID access requires com.termux.api APK companion or Android Bridge with Location permission enabled on Android 16.",
        "requirements": ["com.termux.api APK", "ACCESS_FINE_LOCATION"],
    }
