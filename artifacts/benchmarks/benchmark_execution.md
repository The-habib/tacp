# Benchmark Suite: benchmark_execution
- **Timestamp:** 2026-09-26T08:27:53Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 371.69 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `exec_raw_subprocess_echo` | 30 | 7.873 | 8.967 | 11.051 | 11.324 | 13.133 | 9.359 |
| `exec_process_list_e2e` | 20 | 4.211 | 5.825 | 9.175 | 9.175 | 9.263 | 6.594 |
| `exec_raw_process_service_list` | 20 | 1.886 | 2.031 | 3.424 | 3.424 | 4.070 | 2.299 |
