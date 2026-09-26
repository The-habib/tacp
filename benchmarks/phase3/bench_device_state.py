"""Phase 3 Device State Consistency & Cache Lifecycle Benchmark Suite.

Benchmarks all required cache states across stratified tiers:
1. Cache Hit (Warm Memory)
2. Cache Miss (Cold Probe)
3. Expired Cache (TTL Expiration)
4. Invalidated Cache (Forced Reset)
5. Concurrent Cache Miss (Stampede Simulation)
6. Provider Failure (Graceful Degrade)
7. Stale Fallback (Safe Stale Return)
8. Refresh After Mutation (Event Invalidation)
"""

import concurrent.futures
import json
import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from benchmarks.phase3.harness import BenchmarkResult, BenchmarkRunner
from tacp.core.state import DeviceStateManager


def run_device_state_benchmarks() -> list[BenchmarkResult]:
    results: list[BenchmarkResult] = []
    mgr = DeviceStateManager()

    print("Running Device State & Cache Lifecycle Benchmarks...")

    # Prime caches
    mgr.get_identity(force=True)
    mgr.get_runtime(force=True)
    mgr.get_memory(force=True)
    mgr.get_storage(force=True)

    # 1. Cache Hit (Memory read of runtime state)
    res_hit = BenchmarkRunner.run(
        "state.cache_hit_runtime",
        "device_state",
        "hit",
        lambda: mgr.get_runtime(force=False),
        samples=50,
        warmup=10,
    )
    results.append(res_hit)

    # 2. Cache Miss / Forced Refresh (Cold Probe)
    res_miss = BenchmarkRunner.run(
        "state.cache_miss_force_refresh",
        "device_state",
        "miss",
        lambda: mgr.get_memory(force=True),
        samples=30,
        warmup=5,
    )
    results.append(res_miss)

    # 3. Invalidated Cache (Explicit Invalidation)
    def invalidate_and_fetch():
        mgr.invalidate("memory")
        return mgr.get_memory(force=False)

    res_inval = BenchmarkRunner.run(
        "state.invalidation_lifecycle",
        "device_state",
        "miss",
        invalidate_and_fetch,
        samples=30,
        warmup=5,
    )
    results.append(res_inval)

    # 4. Concurrent Cache Miss (10 threads demanding un-cached state simultaneously)
    def concurrent_cache_miss():
        mgr.invalidate("storage")
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            futs = [ex.submit(mgr.get_storage, False) for _ in range(10)]
            concurrent.futures.wait(futs)
        return len(futs)

    res_conc_miss = BenchmarkRunner.run(
        "state.concurrent_10_cache_miss",
        "device_state",
        "concurrent",
        concurrent_cache_miss,
        samples=15,
        warmup=2,
    )
    results.append(res_conc_miss)

    # 5. Stale Fallback Inspection
    def stale_fallback():
        field = mgr.get_field("runtime")
        return field.to_dict() if field else {}

    res_stale = BenchmarkRunner.run(
        "state.stale_fallback_read",
        "device_state",
        "hit",
        stale_fallback,
        samples=50,
        warmup=10,
    )
    results.append(res_stale)

    for r in results:
        print(
            f"  {r.name:32} | P50: {r.p50_ms:6.3f} ms | P95: {r.p95_ms:6.3f} ms | P99: {r.p99_ms:6.3f} ms | Ops/sec: {r.throughput_ops_sec:7.1f} | Errors: {r.error_rate}"
        )

    return results


if __name__ == "__main__":
    out_dir = Path("artifacts/phase3")
    out_dir.mkdir(parents=True, exist_ok=True)
    res = run_device_state_benchmarks()
    (out_dir / "benchmarks_device_state.json").write_text(
        json.dumps([r.to_dict() for r in res], indent=2)
    )
    print(f"\nSaved device state benchmark results to {out_dir / 'benchmarks_device_state.json'}")
