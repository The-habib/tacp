# Benchmark Suite: benchmark_execution
- **Timestamp:** 2026-09-26T11:00:42Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 469.09 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `exec_raw_subprocess_echo` | 30 | 7.251 | 8.584 | 11.724 | 13.441 | 49.977 | 10.251 |
| `exec_process_list_e2e` | 20 | 4.553 | 6.424 | 17.974 | 17.974 | 39.516 | 9.052 |
| `exec_raw_process_service_list` | 20 | 7.096 | 7.524 | 9.864 | 9.864 | 9.996 | 7.806 |
