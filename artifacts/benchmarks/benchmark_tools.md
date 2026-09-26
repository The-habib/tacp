# Benchmark Suite: benchmark_tools
- **Timestamp:** 2026-09-26T11:03:56Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 469.09 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `tool_system_inspect_e2e` | 50 | 0.545 | 3.206 | 5.562 | 6.792 | 118.570 | 5.568 |
| `tool_system_health_e2e` | 50 | 0.234 | 1.036 | 2.078 | 2.140 | 2.591 | 1.100 |
| `tool_device_info_e2e` | 50 | 0.978 | 1.452 | 2.267 | 5.096 | 5.209 | 1.631 |
| `tool_storage_overview_e2e` | 30 | 0.360 | 0.441 | 1.045 | 1.169 | 1.543 | 0.577 |
| `tool_device_snapshot_e2e` | 20 | 0.720 | 0.829 | 1.973 | 1.973 | 3.924 | 1.092 |
| `latency_class_name_normalization` | 200 | 0.001 | 0.001 | 0.001 | 0.001 | 0.001 | 0.001 |
| `latency_class_registry_execute_tool` | 50 | 0.353 | 0.431 | 0.597 | 0.686 | 1.142 | 0.464 |
| `latency_class_raw_system_inspect` | 100 | 0.125 | 0.128 | 0.139 | 0.188 | 0.262 | 0.132 |
| `latency_class_audit_record_event` | 50 | 0.104 | 0.141 | 0.214 | 0.571 | 24.702 | 0.647 |
