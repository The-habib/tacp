# Benchmark Suite: benchmark_concurrency_matrix
- **Timestamp:** 2026-09-26T11:04:56Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 469.09 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `read_only_concurrency_1` | 10 | 0.002 | 0.002 | 0.015 | 0.015 | 3.196 | 0.323 |
| `read_only_concurrency_2` | 20 | 0.002 | 0.002 | 0.012 | 0.012 | 0.022 | 0.004 |
| `read_only_concurrency_5` | 50 | 0.002 | 0.002 | 0.004 | 0.013 | 0.024 | 0.003 |
| `read_only_concurrency_10` | 100 | 0.002 | 0.002 | 0.013 | 0.023 | 0.025 | 0.005 |
| `read_only_concurrency_25` | 150 | 0.002 | 0.002 | 0.010 | 0.015 | 0.030 | 0.003 |
| `read_only_concurrency_50` | 150 | 0.002 | 0.002 | 0.010 | 0.015 | 0.068 | 0.004 |
| `filesystem_concurrency_1` | 10 | 3.278 | 4.495 | 15.245 | 15.245 | 22.427 | 7.332 |
| `filesystem_concurrency_2` | 20 | 5.866 | 7.456 | 26.154 | 26.154 | 27.494 | 10.345 |
| `filesystem_concurrency_5` | 50 | 6.053 | 13.591 | 42.079 | 43.216 | 44.039 | 16.508 |
| `filesystem_concurrency_10` | 100 | 3.784 | 15.508 | 311.421 | 321.463 | 323.276 | 50.111 |
| `filesystem_concurrency_25` | 150 | 6.242 | 46.703 | 226.117 | 230.250 | 231.536 | 76.927 |
| `filesystem_concurrency_50` | 150 | 10.376 | 157.783 | 317.958 | 338.841 | 435.468 | 148.330 |
| `device_concurrency_1` | 10 | 0.872 | 1.100 | 4.652 | 4.652 | 64.760 | 7.995 |
| `device_concurrency_2` | 20 | 2.712 | 5.715 | 138.759 | 138.759 | 163.154 | 21.023 |
| `device_concurrency_5` | 50 | 2.304 | 10.299 | 19.880 | 22.071 | 29.489 | 11.413 |
| `device_concurrency_10` | 100 | 8.948 | 19.763 | 228.907 | 230.599 | 230.792 | 41.237 |
| `device_concurrency_25` | 150 | 25.386 | 65.380 | 334.218 | 336.093 | 337.906 | 106.743 |
| `device_concurrency_50` | 150 | 2.031 | 192.388 | 488.650 | 500.622 | 501.469 | 234.925 |
| `snapshot_concurrency_1` | 10 | 0.659 | 0.733 | 1.224 | 1.224 | 161.068 | 16.836 |
| `snapshot_concurrency_2` | 20 | 2.182 | 3.528 | 3.893 | 3.893 | 5.583 | 3.488 |
| `snapshot_concurrency_5` | 50 | 1.006 | 10.263 | 301.085 | 303.897 | 304.001 | 40.106 |
| `snapshot_concurrency_10` | 100 | 9.151 | 14.681 | 43.617 | 52.690 | 52.983 | 18.037 |
| `snapshot_concurrency_25` | 150 | 21.527 | 74.301 | 498.434 | 501.335 | 517.161 | 142.139 |
| `snapshot_concurrency_50` | 150 | 5.067 | 143.458 | 219.762 | 221.347 | 222.722 | 141.316 |
| `database_system_health_concurrency_1` | 10 | 0.646 | 0.750 | 1.637 | 1.637 | 4.135 | 1.278 |
| `database_system_health_concurrency_2` | 20 | 0.881 | 1.962 | 9.061 | 9.061 | 16.137 | 3.276 |
| `database_system_health_concurrency_5` | 50 | 0.535 | 3.978 | 23.633 | 34.127 | 34.373 | 6.548 |
| `database_system_health_concurrency_10` | 100 | 2.783 | 17.302 | 59.931 | 63.921 | 64.759 | 19.012 |
| `database_system_health_concurrency_25` | 150 | 1.657 | 22.091 | 171.463 | 173.258 | 226.943 | 47.166 |
| `database_system_health_concurrency_50` | 150 | 39.407 | 123.498 | 314.632 | 316.682 | 316.876 | 159.550 |
