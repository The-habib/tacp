"""Phase 3 Soak & Resource Leak Benchmark (1,000 cycles)."""

import gc
import json
import os
import threading
import time
from pathlib import Path
from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import create_mcp_server
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database


def get_rss_kb() -> int:
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except Exception:
        pass
    return 0


def get_open_fds() -> int:
    try:
        return len(os.listdir("/proc/self/fd"))
    except Exception:
        return 0


def run_soak_test(cycles: int = 1000, duration_minutes: float = 0.0, pace_hz: float = 0.0):
    config = TacpConfig.load()
    db = Database(Path("/data/data/com.termux/files/home/.tacp/tacp.db"))
    server = create_mcp_server(config, db)

    tools_to_cycle = [
        ("tools/list", {}),
        ("tools/call", {"name": "system.health", "arguments": {}}),
        ("tools/call", {"name": "system.inspect", "arguments": {}}),
        ("tools/call", {"name": "device.telemetry.snapshot", "arguments": {}}),
        ("tools/call", {"name": "workspace.list", "arguments": {}}),
    ]

    gc.collect()
    start_rss_kb = get_rss_kb()
    start_fds = get_open_fds()
    start_threads = threading.active_count()
    start_time = time.perf_counter()

    milestones = []
    mode_str = f"{duration_minutes:.1f} minutes timed soak" if duration_minutes > 0 else f"{cycles} cycles burst soak"
    print(f"Starting Soak Test: {mode_str}. Baseline RSS: {start_rss_kb/1024:.2f} MB, FDs: {start_fds}, Threads: {start_threads}")

    i = 0
    duration_s = duration_minutes * 60.0
    sleep_delay = 1.0 / pace_hz if pace_hz > 0 else 0.0

    while True:
        i += 1
        method, params = tools_to_cycle[i % len(tools_to_cycle)]
        req = McpRequest(id=i, method=method, params=params)
        resp = server.handle_request(req)
        assert resp is not None

        if sleep_delay > 0:
            time.sleep(sleep_delay)

        elapsed = time.perf_counter() - start_time
        should_stop = False
        if duration_s > 0:
            if elapsed >= duration_s:
                should_stop = True
        else:
            if i >= cycles:
                should_stop = True

        if i % 200 == 0 or should_stop:
            current_rss_kb = get_rss_kb()
            current_fds = get_open_fds()
            milestones.append({
                "cycle": i,
                "elapsed_s": round(elapsed, 2),
                "rss_mb": round(current_rss_kb / 1024.0, 2),
                "delta_rss_mb": round((current_rss_kb - start_rss_kb) / 1024.0, 2),
                "fds": current_fds,
                "threads": threading.active_count(),
            })
            print(f"[{elapsed:.1f}s] Cycle {i}: RSS = {current_rss_kb/1024:.2f} MB (Delta: {(current_rss_kb - start_rss_kb)/1024:.2f} MB), FDs: {current_fds}")

        if should_stop:
            break

    gc.collect()
    final_rss_kb = get_rss_kb()
    final_fds = get_open_fds()
    final_threads = threading.active_count()
    total_elapsed_s = time.perf_counter() - start_time
    delta_rss_mb = (final_rss_kb - start_rss_kb) / 1024.0

    report = {
        "mode": "endurance" if duration_minutes > 0 else "burst",
        "total_cycles": i,
        "duration_seconds": round(total_elapsed_s, 2),
        "throughput_req_per_sec": round(i / total_elapsed_s, 2),
        "start_rss_mb": round(start_rss_kb / 1024.0, 2),
        "final_rss_mb": round(final_rss_kb / 1024.0, 2),
        "net_leak_mb": round(delta_rss_mb, 2),
        "leak_per_request_kb": round(((final_rss_kb - start_rss_kb) / i), 4) if i > 0 else 0.0,
        "fd_leak": final_fds - start_fds,
        "thread_leak": final_threads - start_threads,
        "milestones": milestones,
        "leak_threshold_passed": delta_rss_mb < 5.0,
    }

    os.makedirs("artifacts/phase3", exist_ok=True)
    with open("artifacts/phase3/soak_test_report.json", "w") as f:
        json.dump(report, f, indent=2)

    print("Soak Test Complete:")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TACP Soak & Resource Leak Benchmark")
    parser.add_argument("--cycles", type=int, default=1000, help="Total request cycles (burst mode)")
    parser.add_argument("--duration-minutes", type=float, default=0.0, help="Run duration in minutes (endurance mode)")
    parser.add_argument("--pace-hz", type=float, default=0.0, help="Target request frequency (ops/sec)")
    args = parser.parse_args()
    run_soak_test(cycles=args.cycles, duration_minutes=args.duration_minutes, pace_hz=args.pace_hz)
