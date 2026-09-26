# TACP Comprehensive Benchmark Report: BASELINE-REPORT
- **Timestamp:** 2026-09-26T08:30:27Z
- **Platform:** Android-16-aarch64-64bit
- **Architecture:** aarch64
- **Python Version:** 3.14.6
- **Base RSS:** 371.69 MB | **Final RSS:** 371.69 MB

| Metric / Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `mcp_server_factory_creation` | 20 | 60.180 | 78.242 | 134.855 | 134.855 | 136.990 | 87.886 |
| `mcp_initialize_handshake` | 100 | 0.002 | 0.002 | 0.003 | 0.004 | 0.009 | 0.002 |
| `mcp_tools_list_dispatch` | 50 | 0.168 | 0.170 | 0.182 | 0.226 | 0.231 | 0.174 |
| `mcp_resources_list_dispatch` | 50 | 0.003 | 0.003 | 0.004 | 0.004 | 0.004 | 0.004 |
| `mcp_prompts_list_dispatch` | 50 | 0.002 | 0.002 | 0.003 | 0.003 | 0.003 | 0.002 |
| `mcp_tools_list_serialization` | 100 | 0.270 | 0.274 | 0.332 | 0.383 | 0.390 | 0.283 |
| `tool_system_inspect_e2e` | 50 | 2.140 | 2.930 | 5.609 | 6.859 | 7.530 | 3.374 |
| `tool_system_health_e2e` | 50 | 1.629 | 2.239 | 3.628 | 3.936 | 8.457 | 2.473 |
| `tool_device_info_e2e` | 50 | 151.369 | 235.758 | 432.397 | 459.596 | 556.149 | 285.777 |
| `tool_storage_overview_e2e` | 30 | 1.962 | 2.549 | 3.794 | 4.547 | 6.751 | 2.749 |
| `tool_device_snapshot_e2e` | 20 | 244.550 | 336.491 | 395.187 | 395.187 | 399.056 | 335.402 |
| `latency_class_name_normalization` | 200 | 0.011 | 0.011 | 0.012 | 0.013 | 0.076 | 0.011 |
| `latency_class_registry_execute_tool` | 50 | 2.092 | 3.620 | 7.120 | 9.031 | 16.730 | 4.269 |
| `latency_class_raw_system_inspect` | 100 | 0.148 | 0.189 | 1.018 | 2.294 | 3.151 | 0.339 |
| `latency_class_audit_record_event` | 50 | 1.475 | 4.824 | 13.998 | 22.161 | 23.180 | 6.474 |
| `fs_stat_mcp_e2e` | 50 | 0.860 | 1.063 | 1.328 | 1.712 | 2.240 | 1.114 |
| `fs_raw_os_stat` | 100 | 0.004 | 0.005 | 0.007 | 0.007 | 0.009 | 0.005 |
| `fs_read_1k_mcp_e2e` | 50 | 0.983 | 1.375 | 2.082 | 2.344 | 26.684 | 2.019 |
| `fs_read_100k_mcp_e2e` | 30 | 7.148 | 7.847 | 9.273 | 10.080 | 10.764 | 8.041 |
| `fs_list_50_files_mcp_e2e` | 30 | 4.365 | 4.726 | 5.317 | 5.612 | 5.686 | 4.794 |
| `fs_search_mcp_e2e` | 20 | 12.782 | 13.748 | 18.716 | 18.716 | 24.702 | 14.703 |
| `policy_evaluate_read_only` | 100 | 0.004 | 0.004 | 0.004 | 0.005 | 0.005 | 0.004 |
| `policy_evaluate_mutation_denied` | 100 | 0.004 | 0.004 | 0.004 | 0.005 | 0.007 | 0.004 |
| `token_verify_hash_and_db` | 50 | 0.065 | 0.070 | 0.114 | 0.117 | 0.154 | 0.076 |
| `db_connection_open_close` | 30 | 0.709 | 0.853 | 1.222 | 1.256 | 1.381 | 0.908 |
| `db_simple_select_query` | 100 | 0.007 | 0.008 | 0.011 | 0.019 | 0.045 | 0.009 |
| `db_audit_insert_with_hash_chain` | 50 | 0.118 | 0.148 | 0.523 | 0.626 | 0.938 | 0.240 |
| `db_audit_chain_verify_integrity` | 20 | 35.931 | 36.349 | 36.892 | 36.892 | 45.605 | 36.930 |
| `exec_raw_subprocess_echo` | 30 | 9.940 | 13.287 | 16.891 | 21.424 | 26.515 | 14.088 |
| `exec_process_list_e2e` | 20 | 2.477 | 2.892 | 3.097 | 3.097 | 3.215 | 2.843 |
| `exec_raw_process_service_list` | 20 | 1.931 | 2.208 | 2.875 | 2.875 | 3.894 | 2.376 |
| `http_local_health_probe` | 30 | 2.110 | 2.980 | 5.725 | 6.600 | 8.915 | 3.633 |
| `http_local_unauth_rejection_speed` | 50 | 2.413 | 3.317 | 5.761 | 6.622 | 8.257 | 3.765 |
| `http_local_auth_initialize` | 30 | 5.450 | 6.939 | 11.467 | 16.862 | 19.589 | 7.770 |
| `http_local_auth_system_inspect_call` | 30 | 6.113 | 9.478 | 26.849 | 34.396 | 37.210 | 12.049 |
| `remote_https_health_probe_rtt` | 10 | 196.947 | 213.882 | 671.211 | 671.211 | 1329.959 | 390.293 |
| `companion_probe_all_forced` | 20 | 68.709 | 89.474 | 141.845 | 141.845 | 146.152 | 96.370 |
| `companion_probe_all_cached` | 100 | 62.280 | 88.144 | 127.859 | 143.864 | 145.194 | 92.382 |
| `backend_probe_termux` | 30 | 0.022 | 0.024 | 0.092 | 0.152 | 0.155 | 0.036 |
| `backend_probe_android_shell` | 30 | 0.291 | 0.305 | 0.385 | 0.400 | 0.414 | 0.319 |
| `backend_probe_termux_api` | 30 | 36.864 | 46.819 | 90.674 | 92.053 | 92.335 | 52.492 |
| `backend_probe_shizuku` | 30 | 12.843 | 16.022 | 35.085 | 37.336 | 56.794 | 19.617 |
| `backend_probe_root` | 30 | 6.299 | 7.755 | 16.217 | 17.101 | 37.409 | 9.573 |
| `registry_list_all_68_capabilities` | 20 | 0.384 | 0.408 | 0.526 | 0.526 | 0.658 | 0.424 |
