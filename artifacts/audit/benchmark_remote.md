# Benchmark Suite: benchmark_remote
- **Timestamp:** 2026-09-26T11:00:47Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 469.09 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `http_local_health_probe` | 30 | 2.428 | 2.959 | 7.022 | 7.044 | 42.799 | 4.778 |
| `http_local_unauth_rejection_speed` | 50 | 3.775 | 4.817 | 6.447 | 8.901 | 9.646 | 5.135 |
| `http_local_auth_initialize` | 30 | 4.110 | 5.206 | 12.679 | 18.083 | 32.273 | 7.248 |
| `http_local_auth_system_inspect_call` | 30 | 9.522 | 11.620 | 32.163 | 37.548 | 48.456 | 16.661 |
| `remote_https_health_probe_rtt` | 10 | 197.885 | 219.049 | 226.334 | 226.334 | 1182.025 | 311.275 |
