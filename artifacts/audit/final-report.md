# TACP Comprehensive Benchmark Report: FINAL-REPORT
- **Timestamp:** 2026-09-26T09:01:23Z
- **Platform:** Android-16-aarch64-64bit
- **Architecture:** aarch64
- **Python Version:** 3.14.6
- **Base RSS:** 469.09 MB | **Final RSS:** 469.09 MB

| Metric / Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `mcp_server_factory_creation` | 20 | 1.617 | 1.881 | 2.206 | 2.206 | 2.570 | 1.954 |
| `mcp_initialize_handshake` | 100 | 0.004 | 0.004 | 0.005 | 0.007 | 0.008 | 0.005 |
| `mcp_tools_list_dispatch` | 50 | 0.003 | 0.003 | 0.004 | 0.004 | 0.005 | 0.003 |
| `mcp_resources_list_dispatch` | 50 | 0.007 | 0.007 | 0.007 | 0.008 | 0.008 | 0.007 |
| `mcp_prompts_list_dispatch` | 50 | 0.004 | 0.004 | 0.005 | 0.005 | 0.006 | 0.005 |
| `mcp_tools_list_serialization` | 100 | 0.475 | 0.488 | 0.561 | 0.598 | 0.681 | 0.497 |
| `tool_system_inspect_e2e` | 50 | 1.569 | 3.631 | 4.660 | 20.971 | 49.365 | 4.906 |
| `tool_system_health_e2e` | 50 | 0.494 | 0.605 | 1.619 | 1.786 | 6.770 | 0.838 |
| `tool_device_info_e2e` | 50 | 11.469 | 29.195 | 49.382 | 53.285 | 54.681 | 28.958 |
| `tool_storage_overview_e2e` | 30 | 2.409 | 2.736 | 8.012 | 13.788 | 33.551 | 4.879 |
| `tool_device_snapshot_e2e` | 20 | 155.065 | 261.931 | 327.276 | 327.276 | 362.043 | 260.163 |
| `latency_class_name_normalization` | 200 | 0.003 | 0.003 | 0.003 | 0.004 | 0.034 | 0.003 |
| `latency_class_registry_execute_tool` | 50 | 0.884 | 1.424 | 3.631 | 3.905 | 4.803 | 1.946 |
| `latency_class_raw_system_inspect` | 100 | 0.315 | 0.332 | 0.438 | 0.511 | 0.548 | 0.353 |
| `latency_class_audit_record_event` | 50 | 0.251 | 0.402 | 0.719 | 1.450 | 38.093 | 1.194 |
| `fs_stat_mcp_e2e` | 50 | 0.861 | 1.200 | 1.792 | 7.582 | 17.215 | 1.732 |
| `fs_raw_os_stat` | 100 | 0.006 | 0.007 | 0.007 | 0.007 | 0.008 | 0.007 |
| `fs_read_1k_mcp_e2e` | 50 | 1.834 | 2.333 | 8.649 | 20.327 | 45.526 | 4.009 |
| `fs_read_100k_mcp_e2e` | 30 | 10.538 | 11.377 | 17.114 | 17.782 | 18.546 | 12.300 |
| `fs_list_50_files_mcp_e2e` | 30 | 3.779 | 4.509 | 8.149 | 8.163 | 10.918 | 5.053 |
| `fs_search_mcp_e2e` | 20 | 16.267 | 19.720 | 30.146 | 30.146 | 40.449 | 21.482 |
| `policy_evaluate_read_only` | 100 | 0.006 | 0.013 | 0.016 | 0.029 | 0.088 | 0.013 |
| `policy_evaluate_mutation_denied` | 100 | 0.013 | 0.013 | 0.014 | 0.014 | 0.014 | 0.013 |
| `token_verify_hash_and_db` | 50 | 0.010 | 0.010 | 0.011 | 0.012 | 0.014 | 0.011 |
| `db_connection_open_close` | 30 | 1.174 | 1.390 | 3.722 | 3.802 | 4.429 | 1.744 |
| `db_simple_select_query` | 100 | 0.010 | 0.010 | 0.012 | 0.022 | 0.023 | 0.011 |
| `db_audit_insert_with_hash_chain` | 50 | 0.186 | 0.314 | 0.698 | 1.012 | 52.126 | 1.419 |
| `db_audit_chain_verify_integrity` | 20 | 77.753 | 112.478 | 133.918 | 133.918 | 152.333 | 112.030 |
| `exec_raw_subprocess_echo` | 30 | 12.875 | 15.872 | 37.428 | 39.086 | 42.813 | 19.438 |
| `exec_process_list_e2e` | 20 | 4.132 | 4.838 | 6.351 | 6.351 | 8.352 | 5.021 |
| `exec_raw_process_service_list` | 20 | 4.047 | 5.046 | 8.704 | 8.704 | 8.780 | 5.524 |
| `http_local_health_probe` | 30 | 4.341 | 5.626 | 16.785 | 18.532 | 30.944 | 7.488 |
| `http_local_unauth_rejection_speed` | 50 | 4.123 | 5.934 | 11.680 | 24.149 | 25.769 | 7.353 |
| `http_local_auth_initialize` | 30 | 5.891 | 8.106 | 31.102 | 32.634 | 34.200 | 10.771 |
| `http_local_auth_system_inspect_call` | 30 | 10.984 | 12.802 | 28.216 | 32.678 | 34.709 | 16.584 |
| `remote_https_health_probe_rtt` | 10 | 208.470 | 218.341 | 1025.138 | 1025.138 | 1079.354 | 447.489 |
| `companion_probe_all_forced` | 20 | 71.842 | 97.858 | 135.899 | 135.899 | 137.252 | 101.571 |
| `companion_probe_all_cached` | 100 | 0.022 | 0.023 | 0.024 | 0.026 | 0.086 | 0.024 |
| `backend_probe_termux` | 30 | 0.034 | 0.035 | 0.037 | 0.038 | 0.038 | 0.035 |
| `backend_probe_android_shell` | 30 | 0.441 | 0.447 | 0.555 | 0.560 | 0.638 | 0.462 |
| `backend_probe_termux_api` | 30 | 41.344 | 74.043 | 116.179 | 135.485 | 142.000 | 78.680 |
| `backend_probe_shizuku` | 30 | 14.548 | 18.162 | 63.505 | 64.449 | 64.805 | 31.502 |
| `backend_probe_root` | 30 | 7.917 | 18.450 | 39.680 | 39.841 | 41.284 | 23.014 |
| `registry_list_all_68_capabilities` | 20 | 0.920 | 0.935 | 1.110 | 1.110 | 1.201 | 0.971 |
| `concurrency_1_clients_latency` | 10 | 0.010 | 3.577 | 23.396 | 23.396 | 54.695 | 12.650 |
| `concurrency_1_clients_throughput_rps` | 10 | 67.267 | 67.267 | 67.267 | 67.267 | 67.267 | 67.267 |
| `concurrency_5_clients_latency` | 50 | 0.006 | 7.158 | 41.231 | 52.421 | 58.108 | 12.890 |
| `concurrency_5_clients_throughput_rps` | 50 | 349.830 | 349.830 | 349.830 | 349.830 | 349.830 | 349.830 |
| `concurrency_10_clients_latency` | 100 | 0.007 | 18.381 | 263.335 | 289.911 | 296.684 | 45.630 |
| `concurrency_10_clients_throughput_rps` | 100 | 201.952 | 201.952 | 201.952 | 201.952 | 201.952 | 201.952 |
| `concurrency_25_clients_latency` | 100 | 0.006 | 70.784 | 131.000 | 143.339 | 167.138 | 65.100 |
| `concurrency_25_clients_throughput_rps` | 100 | 290.907 | 290.907 | 290.907 | 290.907 | 290.907 | 290.907 |
