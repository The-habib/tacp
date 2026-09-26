# Benchmark Suite: benchmark_filesystem
- **Timestamp:** 2026-09-26T11:00:39Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 469.09 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `fs_stat_mcp_e2e` | 50 | 0.913 | 1.583 | 2.557 | 28.112 | 39.458 | 3.133 |
| `fs_raw_os_stat` | 100 | 0.004 | 0.004 | 0.006 | 0.007 | 0.008 | 0.005 |
| `fs_read_1k_mcp_e2e` | 50 | 0.538 | 0.597 | 0.697 | 1.157 | 1.157 | 0.625 |
| `fs_read_100k_mcp_e2e` | 30 | 5.332 | 5.514 | 5.733 | 5.790 | 5.874 | 5.546 |
| `fs_list_50_files_mcp_e2e` | 30 | 1.601 | 1.701 | 2.245 | 2.545 | 2.807 | 1.801 |
| `fs_search_mcp_e2e` | 20 | 8.593 | 9.139 | 10.662 | 10.662 | 11.579 | 9.473 |
