# Benchmark Suite: benchmark_companion
- **Timestamp:** 2026-09-26T08:34:57Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 371.69 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `companion_probe_all_forced` | 20 | 61.204 | 84.719 | 107.264 | 107.264 | 108.799 | 84.410 |
| `companion_probe_all_cached` | 100 | 0.024 | 0.025 | 0.027 | 0.030 | 0.103 | 0.026 |
| `backend_probe_termux` | 30 | 0.043 | 0.043 | 0.046 | 0.048 | 0.049 | 0.044 |
| `backend_probe_android_shell` | 30 | 0.551 | 0.673 | 0.746 | 0.757 | 0.854 | 0.679 |
| `backend_probe_termux_api` | 30 | 28.540 | 58.424 | 68.599 | 69.641 | 70.382 | 54.844 |
| `backend_probe_shizuku` | 30 | 11.695 | 16.726 | 33.959 | 36.863 | 39.626 | 19.949 |
| `backend_probe_root` | 30 | 7.931 | 10.062 | 15.531 | 15.675 | 18.570 | 10.617 |
| `registry_list_all_68_capabilities` | 20 | 0.385 | 0.394 | 0.438 | 0.438 | 0.534 | 0.403 |
