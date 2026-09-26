"""Comprehensive Concurrency Matrix Benchmark.

Measures throughput, P50, P95, P99, Max, and error counts across isolated subsystems:
- READ_ONLY
- FILESYSTEM
- DATABASE
- DEVICE
- AUDIT
across client concurrency levels: 1, 2, 5, 10, 25, 50.
"""

from __future__ import annotations

import concurrent.futures
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.common import (
    MetricSummary,
    compute_metrics,
    get_current_rss_mb,
    save_benchmark_result,
)
from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import create_mcp_server
from tacp.infrastructure.config import TacpConfig


def run_isolated_concurrency_test(
    fn_builder: Callable[[int, int], McpRequest],
    server,
    num_clients: int,
    requests_per_client: int,
) -> Tuple[List[int], int, float]:
    """Execute concurrent batch of requests, returning (durations_ns, errors, wall_time_s)."""
    durations_ns: List[int] = []
    errors = 0

    def client_worker(cid: int) -> List[Tuple[int, bool]]:
        res = []
        for rid in range(requests_per_client):
            req = fn_builder(cid, rid)
            t0 = time.perf_counter_ns()
            resp = server.handle_request(req)
            t1 = time.perf_counter_ns()
            is_err = resp.error is not None
            res.append((t1 - t0, is_err))
        return res

    t_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_clients) as ex:
        futures = [ex.submit(client_worker, i) for i in range(num_clients)]
        for f in concurrent.futures.as_completed(futures):
            for d_ns, err in f.result():
                durations_ns.append(d_ns)
                if err:
                    errors += 1
    wall_time = time.perf_counter() - t_start
    return durations_ns, errors, wall_time


def run_matrix(output_dir: Path) -> Dict[str, Any]:
    config = TacpConfig.load()
    server = create_mcp_server(config=config, enable_device_capabilities=True)

    workspaces = server.tool_registry.workspace_service.list_workspaces()
    if not workspaces:
        ws_root = Path.cwd()
        server.tool_registry.workspace_service.register_workspace("matrix-ws", ws_root)
        ws_id = "matrix-ws"
    else:
        ws_id = workspaces[0]["id"]

    # Subsystem builders
    subsystems = {
        "READ_ONLY": lambda cid, rid: McpRequest(
            method="tools/list",
            params={},
            id=cid * 10000 + rid,
        ),
        "FILESYSTEM": lambda cid, rid: McpRequest(
            method="tools/call",
            params={
                "name": "fs.stat",
                "arguments": {"workspace_id": ws_id, "subpath": "README.md"},
            },
            id=cid * 10000 + rid,
        ),
        "DEVICE": lambda cid, rid: McpRequest(
            method="tools/call",
            params={"name": "device.info", "arguments": {}},
            id=cid * 10000 + rid,
        ),
        "SNAPSHOT": lambda cid, rid: McpRequest(
            method="tools/call",
            params={"name": "device.snapshot", "arguments": {}},
            id=cid * 10000 + rid,
        ),
        "DATABASE_SYSTEM_HEALTH": lambda cid, rid: McpRequest(
            method="tools/call",
            params={"name": "system.health", "arguments": {}},
            id=cid * 10000 + rid,
        ),
    }

    client_tiers = [1, 2, 5, 10, 25, 50]
    matrix_results: Dict[str, Any] = {}
    all_metrics: List[MetricSummary] = []

    print(
        f"{'Subsystem':24} | {'Clients':7} | {'Reqs':5} | {'Throughput':11} | {'P50 (ms)':9} | {'P95 (ms)':9} | {'Errors':6}"
    )
    print("-" * 85)

    for sub_name, req_builder in subsystems.items():
        matrix_results[sub_name] = []
        for c in client_tiers:
            reqs_per_c = 10 if c <= 10 else (6 if c <= 25 else 3)
            total = c * reqs_per_c

            durations_ns, errors, wall_s = run_isolated_concurrency_test(
                fn_builder=req_builder,
                server=server,
                num_clients=c,
                requests_per_client=reqs_per_c,
            )
            rps = total / wall_s if wall_s > 0 else 0.0
            summary = compute_metrics(f"{sub_name.lower()}_concurrency_{c}", durations_ns)
            all_metrics.append(summary)

            rec = {
                "clients": c,
                "total_requests": total,
                "throughput_rps": round(rps, 1),
                "p50_ms": summary.p50_ms,
                "p95_ms": summary.p95_ms,
                "max_ms": summary.max_ms,
                "errors": errors,
            }
            matrix_results[sub_name].append(rec)
            print(
                f"{sub_name:24} | {c:7} | {total:5} | {rps:9.1f} rps | {summary.p50_ms:7.3f} ms | {summary.p95_ms:7.3f} ms | {errors:6}"
            )

    out_file = output_dir / "concurrency-matrix.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(matrix_results, f, indent=2)

    save_benchmark_result(
        suite_name="benchmark_concurrency_matrix",
        metrics=all_metrics,
        output_dir=output_dir,
        extra={"rss_mb": get_current_rss_mb()},
    )
    return matrix_results


if __name__ == "__main__":
    out_dir = Path("artifacts/phase2")
    out_dir.mkdir(parents=True, exist_ok=True)
    run_matrix(out_dir)
