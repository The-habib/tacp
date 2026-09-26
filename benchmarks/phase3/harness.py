"""Standardized Scientific Benchmarking Harness for Phase 3.

Provides rigorous, reproducible statistical measurement:
- Sample count & Warmup count
- P50, P90, P95, P99
- Min, Max, Mean, Standard Deviation
- Throughput (ops/sec)
- Error rate
- Payload size (bytes)
- Process RSS (MB)
- Cold vs Warm classification
- Cache state tracking
"""

from __future__ import annotations

import json
import os
import statistics
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class BenchmarkResult:
    name: str
    category: str  # "local", "network", "device_state"
    condition: str  # "cold", "warm", "hit", "miss", "concurrent"
    sample_count: int
    warmup_count: int
    min_ms: float
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    mean_ms: float
    stdev_ms: float
    throughput_ops_sec: float
    error_rate: float
    payload_bytes: int
    rss_start_mb: float
    rss_end_mb: float
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def get_process_rss_mb() -> float:
    try:
        with open(f"/proc/{os.getpid()}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(float(line.split()[1]) / 1024, 2)
    except Exception:
        pass
    return 0.0


class BenchmarkRunner:
    """Runs a benchmark callable under strict, identical statistical conditions."""

    @staticmethod
    def run(
        name: str,
        category: str,
        condition: str,
        fn: Callable[[], Any],
        samples: int = 50,
        warmup: int = 10,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BenchmarkResult:
        rss_start = get_process_rss_mb()

        # Warmup phase (not measured in statistics)
        for _ in range(warmup):
            try:
                fn()
            except Exception:
                pass

        latencies_ms: List[float] = []
        errors = 0
        last_payload_bytes = 0

        t_total_start = time.perf_counter()
        for _ in range(samples):
            t0 = time.perf_counter()
            try:
                out = fn()
                t1 = time.perf_counter()
                latencies_ms.append((t1 - t0) * 1000)
                if isinstance(out, (bytes, str)):
                    last_payload_bytes = len(out)
                elif isinstance(out, dict):
                    last_payload_bytes = len(json.dumps(out))
            except Exception:
                errors += 1
        t_total_elapsed = time.perf_counter() - t_total_start

        rss_end = get_process_rss_mb()

        if not latencies_ms:
            latencies_ms = [0.0]

        latencies_ms.sort()
        n = len(latencies_ms)

        def percentile(p: float) -> float:
            k = (n - 1) * (p / 100.0)
            f = int(k)
            c = min(f + 1, n - 1)
            d0 = latencies_ms[f] * (c - k)
            d1 = latencies_ms[c] * (k - f)
            return round(d0 + d1, 4)

        mean_val = statistics.mean(latencies_ms)
        stdev_val = statistics.stdev(latencies_ms) if n > 1 else 0.0
        throughput = round(n / t_total_elapsed, 2) if t_total_elapsed > 0 else 0.0

        return BenchmarkResult(
            name=name,
            category=category,
            condition=condition,
            sample_count=n,
            warmup_count=warmup,
            min_ms=round(latencies_ms[0], 4),
            p50_ms=percentile(50.0),
            p90_ms=percentile(90.0),
            p95_ms=percentile(95.0),
            p99_ms=percentile(99.0),
            max_ms=round(latencies_ms[-1], 4),
            mean_ms=round(mean_val, 4),
            stdev_ms=round(stdev_val, 4),
            throughput_ops_sec=throughput,
            error_rate=round(errors / samples, 4) if samples > 0 else 0.0,
            payload_bytes=last_payload_bytes,
            rss_start_mb=rss_start,
            rss_end_mb=rss_end,
            metadata=metadata or {},
        )
