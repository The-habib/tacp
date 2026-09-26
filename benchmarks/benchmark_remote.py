"""Benchmark local and remote Streamable HTTP MCP transports."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.common import (
    MetricSummary,
    compute_metrics,
    get_current_rss_mb,
    save_benchmark_result,
    time_callable,
)
from tacp.infrastructure.config import TacpConfig


def run_benchmark(output_dir: Path) -> List[MetricSummary]:
    config = TacpConfig.load()
    token = ""
    remote_url = ""

    # 1. Read prompt file for full raw secret
    prompt_candidates = [
        config.data_dir / "TACP_AGENT_CONNECT_PROMPT.txt",
        REPO_ROOT / "TACP_AGENT_CONNECT_PROMPT.txt",
    ]
    for pc in prompt_candidates:
        if pc.exists():
            for line in pc.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("tacp_sec_") and not line.endswith("..."):
                    token = line
                    break
        if token:
            break

    # 2. Read remote endpoint from connection info
    info_candidates = [
        config.data_dir / "TACP_CONNECTION_INFO.json",
        REPO_ROOT / "TACP_CONNECTION_INFO.json",
    ]
    for ic in info_candidates:
        if ic.exists():
            try:
                d = json.loads(ic.read_text(encoding="utf-8"))
                remote_url = d.get("mcp", {}).get("endpoint", "")
                if remote_url:
                    break
            except Exception:
                pass

    from tacp.control.auth import TokenService
    from tacp.infrastructure.database import Database

    db = Database(config.db_path)
    tok_svc = TokenService(db)
    if not token or tok_svc.validate_token(token) is None:
        _, token = tok_svc.create_token(
            name="benchmark_runner_token",
            scopes=["tacp.read", "tacp.system.read", "tacp.files.read", "tacp.process.read"],
            expires_days=1,
        )

    local_url = "http://127.0.0.1:8765/mcp"
    health_url = "http://127.0.0.1:8765/health"

    metrics: List[MetricSummary] = []

    # 1. Local Health Probe
    def _test_health() -> None:
        req = urllib.request.Request(health_url)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            resp.read()

    d_health = time_callable(_test_health, iterations=30)
    metrics.append(compute_metrics("http_local_health_probe", d_health))

    # 2. Local Unauthenticated Rejection (HTTP 401 Gate)
    def _test_unauth() -> None:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}).encode(
            "utf-8"
        )
        req = urllib.request.Request(
            local_url, data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 401:
                e.read()
            else:
                raise

    d_unauth = time_callable(_test_unauth, iterations=50)
    metrics.append(compute_metrics("http_local_unauth_rejection_speed", d_unauth))

    # 3. Local Authenticated Initialize Request
    if token:

        def _test_auth_init() -> None:
            body = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2026-07-28",
                        "capabilities": {},
                        "clientInfo": {"name": "bench"},
                    },
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                local_url,
                data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                resp.read()

        d_auth_init = time_callable(_test_auth_init, iterations=30)
        metrics.append(compute_metrics("http_local_auth_initialize", d_auth_init))

        # 4. Local Authenticated tools/call: system.inspect
        def _test_auth_call() -> None:
            body = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "system.inspect", "arguments": {}},
                }
            ).encode("utf-8")
            req = urllib.request.Request(
                local_url,
                data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                resp.read()

        d_auth_call = time_callable(_test_auth_call, iterations=30)
        metrics.append(compute_metrics("http_local_auth_system_inspect_call", d_auth_call))

    # 5. Remote HTTPS Endpoint (if reachable)
    if remote_url and token and "trycloudflare.com" in remote_url:

        def _test_remote_health() -> None:
            r_health = remote_url.replace("/mcp", "/health")
            req = urllib.request.Request(r_health)
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                resp.read()

        try:
            d_remote_health = time_callable(_test_remote_health, iterations=10)
            metrics.append(compute_metrics("remote_https_health_probe_rtt", d_remote_health))
        except Exception:
            pass

    save_benchmark_result(
        suite_name="benchmark_remote",
        metrics=metrics,
        output_dir=output_dir,
        extra={"rss_mb": get_current_rss_mb()},
    )
    return metrics


if __name__ == "__main__":
    out = Path("artifacts/benchmarks")
    results = run_benchmark(out)
    for m in results:
        print(
            f"{m.name:34} | P50: {m.p50_ms:6.3f} ms | P95: {m.p95_ms:6.3f} ms | Max: {m.max_ms:6.3f} ms"
        )
