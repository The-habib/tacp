# Benchmark Suite: benchmark_concurrency
- **Timestamp:** 2026-09-26T11:00:55Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 469.09 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `concurrency_1_clients_latency` | 10 | 0.004 | 1.041 | 16.040 | 16.040 | 37.926 | 7.507 |
| `concurrency_1_clients_throughput_rps` | 10 | 119.927 | 119.927 | 119.927 | 119.927 | 119.927 | 119.927 |
| `concurrency_5_clients_latency` | 50 | 0.004 | 3.457 | 29.886 | 33.778 | 39.275 | 9.192 |
| `concurrency_5_clients_throughput_rps` | 50 | 479.901 | 479.901 | 479.901 | 479.901 | 479.901 | 479.901 |
| `concurrency_10_clients_latency` | 100 | 0.004 | 11.501 | 52.525 | 59.224 | 63.133 | 17.012 |
| `concurrency_10_clients_throughput_rps` | 100 | 479.707 | 479.707 | 479.707 | 479.707 | 479.707 | 479.707 |
| `concurrency_25_clients_latency` | 100 | 0.004 | 35.489 | 86.894 | 100.346 | 100.440 | 36.901 |
| `concurrency_25_clients_throughput_rps` | 100 | 429.480 | 429.480 | 429.480 | 429.480 | 429.480 | 429.480 |
