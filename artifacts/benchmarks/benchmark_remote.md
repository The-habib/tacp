# Benchmark Suite: benchmark_remote
- **Timestamp:** 2026-09-26T11:00:26Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 469.09 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `http_local_health_probe` | 30 | 2.481 | 3.376 | 5.351 | 8.039 | 25.294 | 4.573 |
| `http_local_unauth_rejection_speed` | 50 | 3.697 | 5.479 | 7.129 | 7.363 | 8.913 | 5.520 |
| `http_local_auth_initialize` | 30 | 4.053 | 4.718 | 5.433 | 5.498 | 8.388 | 4.841 |
| `http_local_auth_system_inspect_call` | 30 | 5.764 | 10.463 | 17.710 | 18.064 | 177.208 | 16.124 |
| `remote_https_health_probe_rtt` | 10 | 217.405 | 241.415 | 823.275 | 823.275 | 998.432 | 373.636 |
