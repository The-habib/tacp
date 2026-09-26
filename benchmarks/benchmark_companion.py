"""Benchmark Android companion detection, backend probing, and fallback routing."""

from __future__ import annotations

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
from tacp.backends.manager import BackendManager
from tacp.engine.registry import CapabilityRegistry


def run_benchmark(output_dir: Path) -> List[MetricSummary]:
    bm = BackendManager()
    metrics: List[MetricSummary] = []

    # 1. Full BackendManager.probe_all() (cold/forced)
    d_probe_force = time_callable(lambda: bm.probe_all(force=True), iterations=20)
    metrics.append(compute_metrics("companion_probe_all_forced", d_probe_force))

    # 2. BackendManager.probe_all() (cached)
    d_probe_cached = time_callable(lambda: bm.probe_all(force=False), iterations=100)
    metrics.append(compute_metrics("companion_probe_all_cached", d_probe_cached))

    # 3. Individual Backend Probes:
    # A: Termux backend
    d_termux = time_callable(lambda: bm.termux.probe(force=True), iterations=30)
    metrics.append(compute_metrics("backend_probe_termux", d_termux))

    # B: Android Shell backend
    d_sh = time_callable(lambda: bm.android_shell.probe(force=True), iterations=30)
    metrics.append(compute_metrics("backend_probe_android_shell", d_sh))

    # C: Termux:API companion probe
    d_tapi = time_callable(lambda: bm.termux_api.probe(force=True), iterations=30)
    metrics.append(compute_metrics("backend_probe_termux_api", d_tapi))

    # D: Shizuku probe
    d_shizuku = time_callable(lambda: bm.shizuku.probe(force=True), iterations=30)
    metrics.append(compute_metrics("backend_probe_shizuku", d_shizuku))

    # E: Root probe
    d_root = time_callable(lambda: bm.root.probe(force=True), iterations=30)
    metrics.append(compute_metrics("backend_probe_root", d_root))

    # 4. Capability Registry Full Capability Availability Scan
    reg = CapabilityRegistry(bm)
    d_reg_list = time_callable(lambda: reg.list_capabilities(), iterations=20)
    metrics.append(compute_metrics("registry_list_all_68_capabilities", d_reg_list))

    save_benchmark_result(
        suite_name="benchmark_companion",
        metrics=metrics,
        output_dir=output_dir,
        extra={"rss_mb": get_current_rss_mb()},
    )
    return metrics


if __name__ == "__main__":
    out = Path("artifacts/benchmarks")
    results = run_benchmark(out)
    for m in results:
        print(f"{m.name:34} | P50: {m.p50_ms:6.3f} ms | P95: {m.p95_ms:6.3f} ms | Max: {m.max_ms:6.3f} ms")
