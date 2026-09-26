"""Benchmark filesystem operations, jail resolution, reads, and searches."""

from __future__ import annotations

import os
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
    time_callable,
)
from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import create_mcp_server
from tacp.infrastructure.config import TacpConfig


def setup_test_files(scratch_dir: Path) -> dict:
    scratch_dir.mkdir(parents=True, exist_ok=True)

    # 1KB file
    f_1k = scratch_dir / "file_1k.txt"
    f_1k.write_bytes(b"A" * 1024)

    # 100KB file
    f_100k = scratch_dir / "file_100k.txt"
    f_100k.write_bytes(b"B" * (100 * 1024))

    # 1MB file
    f_1m = scratch_dir / "file_1m.txt"
    f_1m.write_bytes(b"C" * (1024 * 1024))

    # Medium directory with 50 files
    med_dir = scratch_dir / "med_dir"
    med_dir.mkdir(exist_ok=True)
    for i in range(50):
        (med_dir / f"item_{i}.txt").write_text(f"content {i}", encoding="utf-8")

    return {
        "1k": "file_1k.txt",
        "100k": "file_100k.txt",
        "1m": "file_1m.txt",
        "med_dir": "med_dir",
    }


def run_benchmark(output_dir: Path) -> List[MetricSummary]:
    config = TacpConfig.load()
    server = create_mcp_server(config=config, enable_device_capabilities=True)
    metrics: List[MetricSummary] = []

    # Get registered workspace
    workspaces = server.tool_registry.workspace_service.list_workspaces()
    if not workspaces:
        ws_root = Path.cwd()
        server.tool_registry.workspace_service.register_workspace("bench-ws", ws_root)
        ws_id = "bench-ws"
        ws_path = ws_root
    else:
        ws_id = workspaces[0]["id"]
        ws_path = Path(workspaces[0]["root_path"])

    bench_scratch = ws_path / ".bench_scratch"
    paths = setup_test_files(bench_scratch)

    try:
        # 1. fs.stat (MCP tool call)
        req_stat = McpRequest(
            method="tools/call",
            params={"name": "fs.stat", "arguments": {"workspace_id": ws_id, "subpath": f".bench_scratch/{paths['1k']}"}},
            id=20,
        )
        d_stat = time_callable(lambda: server.handle_request(req_stat), iterations=50)
        metrics.append(compute_metrics("fs_stat_mcp_e2e", d_stat))

        # 2. Raw os.stat comparison (baseline without TACP jail/policy/audit)
        raw_stat_path = bench_scratch / paths["1k"]
        d_raw_stat = time_callable(lambda: os.stat(raw_stat_path), iterations=100)
        metrics.append(compute_metrics("fs_raw_os_stat", d_raw_stat))

        # 3. fs.read (1KB)
        req_read_1k = McpRequest(
            method="tools/call",
            params={"name": "fs.read", "arguments": {"workspace_id": ws_id, "subpath": f".bench_scratch/{paths['1k']}"}},
            id=21,
        )
        d_read_1k = time_callable(lambda: server.handle_request(req_read_1k), iterations=50)
        metrics.append(compute_metrics("fs_read_1k_mcp_e2e", d_read_1k))

        # 4. fs.read (100KB)
        req_read_100k = McpRequest(
            method="tools/call",
            params={"name": "fs.read", "arguments": {"workspace_id": ws_id, "subpath": f".bench_scratch/{paths['100k']}"}},
            id=22,
        )
        d_read_100k = time_callable(lambda: server.handle_request(req_read_100k), iterations=30)
        metrics.append(compute_metrics("fs_read_100k_mcp_e2e", d_read_100k))

        # 5. fs.list (med_dir with 50 files)
        req_list_med = McpRequest(
            method="tools/call",
            params={"name": "fs.list", "arguments": {"workspace_id": ws_id, "subpath": f".bench_scratch/{paths['med_dir']}"}},
            id=23,
        )
        d_list_med = time_callable(lambda: server.handle_request(req_list_med), iterations=30)
        metrics.append(compute_metrics("fs_list_50_files_mcp_e2e", d_list_med))

        # 6. fs.search
        req_search = McpRequest(
            method="tools/call",
            params={"name": "fs.search", "arguments": {"workspace_id": ws_id, "subpath": ".bench_scratch", "query": "item_2"}},
            id=24,
        )
        d_search = time_callable(lambda: server.handle_request(req_search), iterations=20)
        metrics.append(compute_metrics("fs_search_mcp_e2e", d_search))

    finally:
        # Cleanup scratch files
        import shutil
        if bench_scratch.exists():
            shutil.rmtree(bench_scratch, ignore_errors=True)

    save_benchmark_result(
        suite_name="benchmark_filesystem",
        metrics=metrics,
        output_dir=output_dir,
        extra={"rss_mb": get_current_rss_mb()},
    )
    return metrics


if __name__ == "__main__":
    out = Path("artifacts/benchmarks")
    results = run_benchmark(out)
    for m in results:
        print(f"{m.name:32} | P50: {m.p50_ms:6.3f} ms | P95: {m.p95_ms:6.3f} ms | Max: {m.max_ms:6.3f} ms")
