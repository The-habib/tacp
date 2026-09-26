"""Shared utilities for reproducible TACP benchmarks on Android/Termux."""

from __future__ import annotations

import json
import os
import platform
import resource
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class MetricSummary:
    name: str
    iterations: int
    min_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    mean_ms: float
    stdev_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_metrics(name: str, durations_ns: List[int]) -> MetricSummary:
    """Compute MIN, P50, P95, P99, MAX, mean, and stdev from nanosecond samples."""
    if not durations_ns:
        return MetricSummary(name, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    ms_list = [ns / 1_000_000.0 for ns in durations_ns]
    ms_list.sort()
    n = len(ms_list)

    def percentile(p: float) -> float:
        idx = int(p * (n - 1))
        return ms_list[idx]

    return MetricSummary(
        name=name,
        iterations=n,
        min_ms=round(ms_list[0], 4),
        p50_ms=round(percentile(0.50), 4),
        p95_ms=round(percentile(0.95), 4),
        p99_ms=round(percentile(0.99), 4),
        max_ms=round(ms_list[-1], 4),
        mean_ms=round(statistics.mean(ms_list), 4),
        stdev_ms=round(statistics.stdev(ms_list) if n > 1 else 0.0, 4),
    )


def time_callable(fn: Callable[[], Any], iterations: int = 50, warmup: int = 5) -> List[int]:
    """Run warmup iterations then record timing for given iterations in nanoseconds."""
    for _ in range(warmup):
        fn()

    durations: List[int] = []
    for _ in range(iterations):
        t0 = time.perf_counter_ns()
        fn()
        t1 = time.perf_counter_ns()
        durations.append(t1 - t0)
    return durations


def get_current_rss_mb() -> float:
    """Return Resident Set Size in megabytes."""
    try:
        # On Linux/Termux, ru_maxrss is in kilobytes
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_maxrss / 1024.0
    except Exception:
        return 0.0


def get_env_metadata() -> Dict[str, Any]:
    """Collect hardware and OS metadata for reproducible baseline audits."""
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "os": platform.system(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "arch": platform.machine(),
        "pid": os.getpid(),
        "rss_mb": round(get_current_rss_mb(), 2),
    }


def save_benchmark_result(
    suite_name: str,
    metrics: List[MetricSummary],
    output_dir: Path,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Save machine-readable JSON and human-readable Markdown."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "suite": suite_name,
        "environment": get_env_metadata(),
        "metrics": [m.to_dict() for m in metrics],
        "extra": extra or {},
    }

    json_path = output_dir / f"{suite_name}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    md_lines = [
        f"# Benchmark Suite: {suite_name}",
        f"- **Timestamp:** {payload['environment']['timestamp']}",
        f"- **Platform:** {payload['environment']['platform']}",
        f"- **Python:** {payload['environment']['python_version']}",
        f"- **Base RSS:** {payload['environment']['rss_mb']} MB",
        "",
        "| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in metrics:
        md_lines.append(
            f"| `{m.name}` | {m.iterations} | {m.min_ms:.3f} | {m.p50_ms:.3f} | {m.p95_ms:.3f} | {m.p99_ms:.3f} | {m.max_ms:.3f} | {m.mean_ms:.3f} |"
        )
    md_lines.append("")

    md_path = output_dir / f"{suite_name}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
