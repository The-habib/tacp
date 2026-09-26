# Benchmark Suite: benchmark_tools
- **Timestamp:** 2026-09-26T11:00:39Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 469.09 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `tool_system_inspect_e2e` | 50 | 0.635 | 1.148 | 1.672 | 1.958 | 8.799 | 1.315 |
| `tool_system_health_e2e` | 50 | 0.267 | 0.361 | 0.932 | 4.597 | 31.381 | 1.141 |
| `tool_device_info_e2e` | 50 | 8.464 | 16.945 | 20.252 | 22.003 | 52.991 | 16.898 |
| `tool_storage_overview_e2e` | 30 | 2.077 | 3.367 | 4.471 | 10.401 | 16.585 | 3.943 |
| `tool_device_snapshot_e2e` | 20 | 111.637 | 167.227 | 264.542 | 264.542 | 273.027 | 173.669 |
| `latency_class_name_normalization` | 200 | 0.001 | 0.001 | 0.001 | 0.001 | 0.002 | 0.001 |
| `latency_class_registry_execute_tool` | 50 | 0.835 | 0.945 | 1.145 | 1.350 | 1.504 | 0.975 |
| `latency_class_raw_system_inspect` | 100 | 0.303 | 0.316 | 0.399 | 0.482 | 0.851 | 0.331 |
| `latency_class_audit_record_event` | 50 | 0.230 | 0.267 | 0.412 | 0.490 | 0.621 | 0.298 |
