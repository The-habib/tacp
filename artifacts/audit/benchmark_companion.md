# Benchmark Suite: benchmark_companion
- **Timestamp:** 2026-09-26T11:00:54Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 469.09 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `companion_probe_all_forced` | 20 | 95.256 | 113.543 | 135.514 | 135.514 | 150.720 | 117.799 |
| `companion_probe_all_cached` | 100 | 0.013 | 0.014 | 0.015 | 0.016 | 0.018 | 0.014 |
| `backend_probe_termux` | 30 | 0.020 | 0.022 | 0.026 | 0.043 | 0.074 | 0.025 |
| `backend_probe_android_shell` | 30 | 0.272 | 0.303 | 0.348 | 0.357 | 0.441 | 0.312 |
| `backend_probe_termux_api` | 30 | 47.911 | 68.476 | 88.695 | 95.298 | 120.522 | 70.401 |
| `backend_probe_shizuku` | 30 | 18.679 | 22.658 | 39.873 | 40.693 | 41.974 | 26.540 |
| `backend_probe_root` | 30 | 5.715 | 6.464 | 26.342 | 29.072 | 32.843 | 10.559 |
| `registry_list_all_68_capabilities` | 20 | 0.294 | 0.298 | 0.330 | 0.330 | 0.349 | 0.303 |
