"""Benchmark 50 requests to disconnected companion: Before vs After Circuit Breaker."""

import json
import statistics
import time

from tacp.backends.companion_transport import HttpCompanionTransport
from tacp.domain.errors import TacpError


def benchmark_circuit_breaker():
    # 1. Without circuit breaker (force failure_threshold=9999 so every request tries TCP socket connect timeout)
    # Using 10ms timeout per request
    transport_no_cb = HttpCompanionTransport(port=59998, failure_threshold=9999)
    times_no_cb = []
    for _ in range(50):
        t0 = time.perf_counter_ns()
        try:
            transport_no_cb.send_request("/test", timeout=0.02)
        except TacpError:
            pass
        t1 = time.perf_counter_ns()
        times_no_cb.append((t1 - t0) / 1_000_000.0)  # ms

    # 2. With circuit breaker (trips to OPEN after 3 failures, then fails fast)
    transport_cb = HttpCompanionTransport(port=59998, failure_threshold=3, recovery_timeout=60.0)
    times_cb = []
    for _ in range(50):
        t0 = time.perf_counter_ns()
        try:
            transport_cb.send_request("/test", timeout=0.02)
        except TacpError:
            pass
        t1 = time.perf_counter_ns()
        times_cb.append((t1 - t0) / 1_000_000.0)  # ms

    # Fail-fast phase only (requests 4-50)
    fail_fast_times = times_cb[3:]

    results = {
        "request_count": 50,
        "without_circuit_breaker": {
            "total_time_ms": round(sum(times_no_cb), 2),
            "p50_ms": round(sorted(times_no_cb)[25], 3),
            "p95_ms": round(sorted(times_no_cb)[47], 3),
            "mean_ms": round(statistics.mean(times_no_cb), 3),
        },
        "with_circuit_breaker_open": {
            "total_time_ms": round(sum(times_cb), 2),
            "p50_fail_fast_ms": round(sorted(fail_fast_times)[len(fail_fast_times) // 2], 4),
            "p95_fail_fast_ms": round(sorted(fail_fast_times)[int(len(fail_fast_times) * 0.95)], 4),
            "mean_fail_fast_ms": round(statistics.mean(fail_fast_times), 4),
        },
        "speedup_factor": f"{statistics.mean(times_no_cb) / statistics.mean(fail_fast_times):.1f}x faster fail-fast",
    }

    print(json.dumps(results, indent=2))
    with open("artifacts/phase3/circuit_breaker_benchmark.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    benchmark_circuit_breaker()
