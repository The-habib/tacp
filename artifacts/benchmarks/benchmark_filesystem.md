# Benchmark Suite: benchmark_filesystem
- **Timestamp:** 2026-09-26T08:48:48Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 469.09 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `fs_stat_mcp_e2e` | 50 | 0.391 | 0.480 | 0.688 | 1.391 | 32.721 | 1.152 |
| `fs_raw_os_stat` | 100 | 0.004 | 0.005 | 0.005 | 0.005 | 0.006 | 0.005 |
| `fs_read_1k_mcp_e2e` | 50 | 0.563 | 0.653 | 0.906 | 1.382 | 1.401 | 0.703 |
| `fs_read_100k_mcp_e2e` | 30 | 5.746 | 5.866 | 6.205 | 6.236 | 6.280 | 5.924 |
| `fs_list_50_files_mcp_e2e` | 30 | 1.700 | 1.802 | 1.959 | 2.312 | 25.562 | 2.622 |
| `fs_search_mcp_e2e` | 20 | 9.052 | 9.241 | 11.460 | 11.460 | 11.702 | 9.607 |
