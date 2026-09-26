"""Benchmark 100 concurrent snapshot requests with SingleFlight stampede prevention."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from tacp.core.coalesce import SingleFlight
from tacp.core.state import DeviceStateManager


def benchmark_singleflight():
    sm = DeviceStateManager.get_default()
    group = SingleFlight()

    raw_executions = 0
    raw_lock = threading.Lock()

    def raw_snapshot():
        nonlocal raw_executions
        with raw_lock:
            raw_executions += 1
        time.sleep(0.02)
        return sm.get_state_snapshot(force=False)

    N = 100

    # 1. Without SingleFlight: 100 concurrent callers
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=N) as ex:
        futures = [ex.submit(raw_snapshot) for _ in range(N)]
        res_no_sf = [f.result() for f in futures]
    t_no_sf = (time.perf_counter() - t0) * 1000.0  # ms

    # 2. With SingleFlight: 100 concurrent callers
    sf_executions = 0
    sf_lock = threading.Lock()

    def sf_snapshot():
        nonlocal sf_executions
        with sf_lock:
            sf_executions += 1
        time.sleep(0.02)
        return sm.get_state_snapshot(force=False)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=N) as ex:
        futures = [ex.submit(group.do, "snapshot_test", sf_snapshot) for _ in range(N)]
        res_with_sf = [f.result() for f in futures]
    t_with_sf = (time.perf_counter() - t0) * 1000.0  # ms

    results = {
        "concurrency": N,
        "without_singleflight": {
            "total_underlying_executions": raw_executions,
            "total_wall_clock_ms": round(t_no_sf, 2),
            "stampede_multiplication": raw_executions,
        },
        "with_singleflight": {
            "total_underlying_executions": sf_executions,
            "total_wall_clock_ms": round(t_with_sf, 2),
            "stampede_multiplication": sf_executions,
            "calls_coalesced": N - sf_executions,
        },
        "improvement": {
            "execution_reduction_factor": f"{raw_executions / sf_executions:.1f}x fewer executions",
            "latency_reduction_pct": f"{(1 - (t_with_sf / t_no_sf)) * 100:.1f}%",
        },
    }

    print(json.dumps(results, indent=2))
    with open("artifacts/phase3/singleflight_benchmark.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    benchmark_singleflight()
