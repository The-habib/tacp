"""Benchmark Fast-Read latency under 50 concurrent mutations with and without Multi-Lane Admission."""

import json
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from tacp.core.admission import AdmissionController, LaneType


def benchmark_admission():
    # 1. Monolithic single-queue simulation (monolithic 32 slots shared by all)
    monolithic_sem = threading.Semaphore(32)
    mono_read_times = []

    def monolithic_slow_mutation():
        with monolithic_sem:
            time.sleep(0.08)  # 80ms mutation lock

    def monolithic_fast_read():
        t0 = time.perf_counter_ns()
        with monolithic_sem:
            time.sleep(0.0001)  # 0.1ms read
        t1 = time.perf_counter_ns()
        mono_read_times.append((t1 - t0) / 1_000_000.0)  # ms

    # Launch 50 concurrent mutations
    ex1 = ThreadPoolExecutor(max_workers=60)
    for _ in range(50):
        ex1.submit(monolithic_slow_mutation)
    time.sleep(0.01)  # ensure mutations acquire slots

    # Measure 50 fast reads during mutation saturation
    read_futures = [ex1.submit(monolithic_fast_read) for _ in range(50)]
    for f in read_futures:
        f.result()
    ex1.shutdown(wait=True)

    # 2. Multi-lane isolated admission
    ac = AdmissionController()
    lane_read_times = []

    def lane_slow_mutation():
        with ac.acquire(LaneType.MUTATION):
            time.sleep(0.08)

    def lane_fast_read():
        t0 = time.perf_counter_ns()
        with ac.acquire(LaneType.FAST_READ):
            time.sleep(0.0001)
        t1 = time.perf_counter_ns()
        lane_read_times.append((t1 - t0) / 1_000_000.0)  # ms

    ex2 = ThreadPoolExecutor(max_workers=60)
    for _ in range(50):
        ex2.submit(lane_slow_mutation)
    time.sleep(0.01)

    read_futures = [ex2.submit(lane_fast_read) for _ in range(50)]
    for f in read_futures:
        f.result()
    ex2.shutdown(wait=True)

    mono_sorted = sorted(mono_read_times)
    lane_sorted = sorted(lane_read_times)

    results = {
        "concurrency_load": "50 concurrent mutations",
        "monolithic_queue": {
            "p50_ms": round(mono_sorted[int(len(mono_sorted) * 0.5)], 3),
            "p95_ms": round(mono_sorted[int(len(mono_sorted) * 0.95)], 3),
            "p99_ms": round(mono_sorted[int(len(mono_sorted) * 0.99)], 3),
            "mean_ms": round(statistics.mean(mono_read_times), 3),
        },
        "multi_lane_isolated": {
            "p50_ms": round(lane_sorted[int(len(lane_sorted) * 0.5)], 3),
            "p95_ms": round(lane_sorted[int(len(lane_sorted) * 0.95)], 3),
            "p99_ms": round(lane_sorted[int(len(lane_sorted) * 0.99)], 3),
            "mean_ms": round(statistics.mean(lane_read_times), 3),
        },
        "improvement": {
            "p50_speedup": f"{mono_sorted[int(len(mono_sorted) * 0.5)] / lane_sorted[int(len(lane_sorted) * 0.5)]:.1f}x faster",
            "p95_speedup": f"{mono_sorted[int(len(mono_sorted) * 0.95)] / lane_sorted[int(len(lane_sorted) * 0.95)]:.1f}x faster",
        },
    }

    print(json.dumps(results, indent=2))
    with open("artifacts/phase3/admission_benchmark.json", "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    benchmark_admission()
