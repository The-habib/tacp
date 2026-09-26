"""Benchmark Cold, Warm, and Stale-Fallback Latencies for all 10 State Fields."""

import time
import json
import statistics
from tacp.core.state import DeviceStateManager

def benchmark_cache_matrix():
    sm = DeviceStateManager.get_default()
    fields = [
        ("selinux", sm.get_selinux),
        ("battery", sm.get_battery),
        ("network", sm.get_network),
        ("packages", sm.get_packages),
        ("companion", sm.get_companion),
        ("memory", sm.get_memory),
        ("storage", sm.get_storage),
        ("processes", sm.get_processes),
        ("audio", sm.get_audio),
        ("screen", sm.get_screen),
    ]

    N_WARM = 100
    N_COLD = 5
    results = {}

    print("Field | Cold P50 (us) | Cold Mean (us) | Warm P50 (us) | Warm Mean (us) | Stale Fallback (us)")
    print("---|---|---|---|---|---")

    for name, getter in fields:
        # 1. Cold measurements (invalidate before each call, force=True)
        cold_times = []
        for _ in range(N_COLD):
            sm.invalidate(name)
            t0 = time.perf_counter_ns()
            getter(force=True)
            t1 = time.perf_counter_ns()
            cold_times.append((t1 - t0) / 1000.0) # microseconds

        # Warm up cache
        getter(force=False)

        # 2. Warm measurements (force=False)
        warm_times = []
        for _ in range(N_WARM):
            t0 = time.perf_counter_ns()
            getter(force=False)
            t1 = time.perf_counter_ns()
            warm_times.append((t1 - t0) / 1000.0) # microseconds

        # 3. Stale fallback measurement (simulate expired entry by backdating timestamp)
        entry = sm._cache.get(name)
        if entry:
            entry["timestamp"] = time.time() - 999999.0 # expired
        t0 = time.perf_counter_ns()
        sm.get_field(name)
        t1 = time.perf_counter_ns()
        stale_us = (t1 - t0) / 1000.0

        cold_sorted = sorted(cold_times)
        warm_sorted = sorted(warm_times)

        cold_p50 = cold_sorted[int(len(cold_sorted) * 0.5)]
        cold_mean = statistics.mean(cold_times)
        warm_p50 = warm_sorted[int(len(warm_sorted) * 0.5)]
        warm_mean = statistics.mean(warm_times)

        results[name] = {
            "cold_p50_us": round(cold_p50, 2),
            "cold_mean_us": round(cold_mean, 2),
            "warm_p50_us": round(warm_p50, 2),
            "warm_mean_us": round(warm_mean, 2),
            "stale_fallback_us": round(stale_us, 2),
        }

        print(f"{name} | {cold_p50:.2f} | {cold_mean:.2f} | {warm_p50:.2f} | {warm_mean:.2f} | {stale_us:.2f}")

    with open('artifacts/phase3/cache_matrix_results.json', 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == '__main__':
    benchmark_cache_matrix()
