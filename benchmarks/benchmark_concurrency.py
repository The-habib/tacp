"""Benchmark concurrent client requests and database contention.

Measures throughput and latencies across 1, 5, 10, and 25 simultaneous clients
performing mixed read and write operations.
"""

from __future__ import annotations

import concurrent.futures
import sys
import time
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
)
from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import create_mcp_server
from tacp.infrastructure.config import TacpConfig


def run_concurrent_client_batch(
    server,
    num_clients: int,
    requests_per_client: int,
    workspace_id: str,
) -> tuple[List[int], int]:
    """Execute requests across concurrent threads, returning (durations_ns, error_count)."""
    durations_ns: List[int] = []
    errors = 0

    def worker(client_idx: int) -> List[tuple[int, bool]]:
        results = []
        for req_idx in range(requests_per_client):
            # Alternate between read-only (tools/list, fs.stat, device.info) and auditing calls
            if req_idx % 3 == 0:
                req = McpRequest(
                    method="tools/call",
                    params={"name": "device.info", "arguments": {}},
                    id=client_idx * 1000 + req_idx,
                )
            elif req_idx % 3 == 1:
                req = McpRequest(
                    method="tools/call",
                    params={"name": "system.inspect", "arguments": {"workspace_id": workspace_id}},
                    id=client_idx * 1000 + req_idx,
                )
            else:
                req = McpRequest(
                    method="tools/list",
                    params={},
                    id=client_idx * 1000 + req_idx,
                )

            t0 = time.perf_counter_ns()
            resp = server.handle_request(req)
            t1 = time.perf_counter_ns()

            is_err = resp.error is not None
            results.append((t1 - t0, is_err))
        return results

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_clients) as executor:
        futures = [executor.submit(worker, i) for i in range(num_clients)]
        for f in concurrent.futures.as_completed(futures):
            for dur, is_err in f.result():
                durations_ns.append(dur)
                if is_err:
                    errors += 1

    return durations_ns, errors


def run_benchmark(output_dir: Path) -> List[MetricSummary]:
    config = TacpConfig.load()
    server = create_mcp_server(config=config, enable_device_capabilities=True)
    metrics: List[MetricSummary] = []

    workspaces = server.tool_registry.workspace_service.list_workspaces()
    if not workspaces:
        ws_root = Path.cwd()
        server.tool_registry.workspace_service.register_workspace("bench-concurrency-ws", ws_root)
        ws_id = "bench-concurrency-ws"
    else:
        ws_id = workspaces[0]["id"]

    concurrency_levels = [1, 5, 10, 25]

    for c in concurrency_levels:
        requests_per_client = 10 if c <= 10 else 4
        total_reqs = c * requests_per_client

        t0 = time.perf_counter()
        durations_ns, error_count = run_concurrent_client_batch(
            server=server,
            num_clients=c,
            requests_per_client=requests_per_client,
            workspace_id=ws_id,
        )
        wall_time_s = time.perf_counter() - t0
        throughput = total_reqs / wall_time_s if wall_time_s > 0 else 0.0

        summary = compute_metrics(f"concurrency_{c}_clients_latency", durations_ns)
        metrics.append(summary)

        # Record throughput metric
        m_thru = MetricSummary(
            name=f"concurrency_{c}_clients_throughput_rps",
            iterations=total_reqs,
            min_ms=throughput,
            p50_ms=throughput,
            p95_ms=throughput,
            p99_ms=throughput,
            max_ms=throughput,
            mean_ms=throughput,
            stdev_ms=0.0,
        )
        metrics.append(m_thru)
        assert error_count == 0, f"Encountered {error_count} errors at concurrency level {c}"

    save_benchmark_result(
        suite_name="benchmark_concurrency",
        metrics=metrics,
        output_dir=output_dir,
        extra={"rss_mb": get_current_rss_mb()},
    )
    return metrics


if __name__ == "__main__":
    out = Path("artifacts/benchmarks")
    results = run_benchmark(out)
    for m in results:
        if "throughput" in m.name:
            print(f"{m.name:42} | Throughput: {m.mean_ms:6.1f} req/s")
        else:
            print(
                f"{m.name:42} | P50: {m.p50_ms:6.3f} ms | P95: {m.p95_ms:6.3f} ms | Max: {m.max_ms:6.3f} ms"
            )
