# TACP Comprehensive Benchmark Report: PHASE2-INITIAL-VERIFICATION
- **Timestamp:** 2026-09-26T11:00:33Z
- **Platform:** Android-16-aarch64-64bit
- **Architecture:** aarch64
- **Python Version:** 3.14.6
- **Base RSS:** 469.09 MB | **Final RSS:** 469.09 MB

| Metric / Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `mcp_server_factory_creation` | 20 | 0.936 | 1.800 | 2.175 | 2.175 | 2.261 | 1.824 |
| `mcp_initialize_handshake` | 100 | 0.002 | 0.002 | 0.003 | 0.004 | 0.004 | 0.002 |
| `mcp_tools_list_dispatch` | 50 | 0.002 | 0.002 | 0.002 | 0.002 | 0.003 | 0.002 |
| `mcp_resources_list_dispatch` | 50 | 0.003 | 0.003 | 0.003 | 0.003 | 0.005 | 0.003 |
| `mcp_prompts_list_dispatch` | 50 | 0.002 | 0.002 | 0.002 | 0.003 | 0.004 | 0.002 |
| `mcp_tools_list_serialization` | 100 | 0.249 | 0.255 | 0.302 | 0.327 | 0.996 | 0.269 |
| `tool_system_inspect_e2e` | 50 | 0.635 | 1.148 | 1.672 | 1.958 | 8.799 | 1.315 |
| `tool_system_health_e2e` | 50 | 0.267 | 0.361 | 0.932 | 4.597 | 31.381 | 1.141 |
| `tool_device_info_e2e` | 50 | 8.464 | 16.945 | 20.252 | 22.003 | 52.991 | 16.898 |
| `tool_storage_overview_e2e` | 30 | 2.077 | 3.367 | 4.471 | 10.401 | 16.585 | 3.943 |
| `tool_device_snapshot_e2e` | 20 | 111.637 | 167.227 | 264.542 | 264.542 | 273.027 | 173.669 |
| `latency_class_name_normalization` | 200 | 0.001 | 0.001 | 0.001 | 0.001 | 0.002 | 0.001 |
| `latency_class_registry_execute_tool` | 50 | 0.835 | 0.945 | 1.145 | 1.350 | 1.504 | 0.975 |
| `latency_class_raw_system_inspect` | 100 | 0.303 | 0.316 | 0.399 | 0.482 | 0.851 | 0.331 |
| `latency_class_audit_record_event` | 50 | 0.230 | 0.267 | 0.412 | 0.490 | 0.621 | 0.298 |
| `fs_stat_mcp_e2e` | 50 | 0.913 | 1.583 | 2.557 | 28.112 | 39.458 | 3.133 |
| `fs_raw_os_stat` | 100 | 0.004 | 0.004 | 0.006 | 0.007 | 0.008 | 0.005 |
| `fs_read_1k_mcp_e2e` | 50 | 0.538 | 0.597 | 0.697 | 1.157 | 1.157 | 0.625 |
| `fs_read_100k_mcp_e2e` | 30 | 5.332 | 5.514 | 5.733 | 5.790 | 5.874 | 5.546 |
| `fs_list_50_files_mcp_e2e` | 30 | 1.601 | 1.701 | 2.245 | 2.545 | 2.807 | 1.801 |
| `fs_search_mcp_e2e` | 20 | 8.593 | 9.139 | 10.662 | 10.662 | 11.579 | 9.473 |
| `policy_evaluate_read_only` | 100 | 0.003 | 0.003 | 0.003 | 0.004 | 0.004 | 0.003 |
| `policy_evaluate_mutation_denied` | 100 | 0.003 | 0.003 | 0.004 | 0.004 | 0.004 | 0.003 |
| `token_verify_hash_and_db` | 50 | 0.003 | 0.003 | 0.003 | 0.003 | 0.004 | 0.003 |
| `db_connection_open_close` | 30 | 0.481 | 1.044 | 1.496 | 1.546 | 1.747 | 1.030 |
| `db_simple_select_query` | 100 | 0.005 | 0.005 | 0.006 | 0.007 | 0.007 | 0.005 |
| `db_audit_insert_with_hash_chain` | 50 | 0.097 | 0.115 | 0.154 | 0.173 | 0.205 | 0.122 |
| `db_audit_chain_verify_integrity` | 20 | 50.423 | 51.258 | 53.466 | 53.466 | 55.833 | 51.615 |
| `exec_raw_subprocess_echo` | 30 | 7.251 | 8.584 | 11.724 | 13.441 | 49.977 | 10.251 |
| `exec_process_list_e2e` | 20 | 4.553 | 6.424 | 17.974 | 17.974 | 39.516 | 9.052 |
| `exec_raw_process_service_list` | 20 | 7.096 | 7.524 | 9.864 | 9.864 | 9.996 | 7.806 |
| `http_local_health_probe` | 30 | 2.428 | 2.959 | 7.022 | 7.044 | 42.799 | 4.778 |
| `http_local_unauth_rejection_speed` | 50 | 3.775 | 4.817 | 6.447 | 8.901 | 9.646 | 5.135 |
| `http_local_auth_initialize` | 30 | 4.110 | 5.206 | 12.679 | 18.083 | 32.273 | 7.248 |
| `http_local_auth_system_inspect_call` | 30 | 9.522 | 11.620 | 32.163 | 37.548 | 48.456 | 16.661 |
| `remote_https_health_probe_rtt` | 10 | 197.885 | 219.049 | 226.334 | 226.334 | 1182.025 | 311.275 |
| `companion_probe_all_forced` | 20 | 95.256 | 113.543 | 135.514 | 135.514 | 150.720 | 117.799 |
| `companion_probe_all_cached` | 100 | 0.013 | 0.014 | 0.015 | 0.016 | 0.018 | 0.014 |
| `backend_probe_termux` | 30 | 0.020 | 0.022 | 0.026 | 0.043 | 0.074 | 0.025 |
| `backend_probe_android_shell` | 30 | 0.272 | 0.303 | 0.348 | 0.357 | 0.441 | 0.312 |
| `backend_probe_termux_api` | 30 | 47.911 | 68.476 | 88.695 | 95.298 | 120.522 | 70.401 |
| `backend_probe_shizuku` | 30 | 18.679 | 22.658 | 39.873 | 40.693 | 41.974 | 26.540 |
| `backend_probe_root` | 30 | 5.715 | 6.464 | 26.342 | 29.072 | 32.843 | 10.559 |
| `registry_list_all_68_capabilities` | 20 | 0.294 | 0.298 | 0.330 | 0.330 | 0.349 | 0.303 |
| `concurrency_1_clients_latency` | 10 | 0.004 | 1.041 | 16.040 | 16.040 | 37.926 | 7.507 |
| `concurrency_1_clients_throughput_rps` | 10 | 119.927 | 119.927 | 119.927 | 119.927 | 119.927 | 119.927 |
| `concurrency_5_clients_latency` | 50 | 0.004 | 3.457 | 29.886 | 33.778 | 39.275 | 9.192 |
| `concurrency_5_clients_throughput_rps` | 50 | 479.901 | 479.901 | 479.901 | 479.901 | 479.901 | 479.901 |
| `concurrency_10_clients_latency` | 100 | 0.004 | 11.501 | 52.525 | 59.224 | 63.133 | 17.012 |
| `concurrency_10_clients_throughput_rps` | 100 | 479.707 | 479.707 | 479.707 | 479.707 | 479.707 | 479.707 |
| `concurrency_25_clients_latency` | 100 | 0.004 | 35.489 | 86.894 | 100.346 | 100.440 | 36.901 |
| `concurrency_25_clients_throughput_rps` | 100 | 429.480 | 429.480 | 429.480 | 429.480 | 429.480 | 429.480 |
