# Benchmark Suite: benchmark_concurrency
- **Timestamp:** 2026-09-26T08:50:30Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 469.09 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `concurrency_1_clients_latency` | 10 | 0.017 | 3.885 | 31.454 | 31.454 | 87.251 | 18.440 |
| `concurrency_1_clients_throughput_rps` | 10 | 52.720 | 52.720 | 52.720 | 52.720 | 52.720 | 52.720 |
| `concurrency_5_clients_latency` | 50 | 0.005 | 8.195 | 36.547 | 42.169 | 44.510 | 12.591 |
| `concurrency_5_clients_throughput_rps` | 50 | 339.396 | 339.396 | 339.396 | 339.396 | 339.396 | 339.396 |
| `concurrency_10_clients_latency` | 100 | 0.005 | 17.857 | 54.951 | 121.893 | 130.091 | 20.979 |
| `concurrency_10_clients_throughput_rps` | 100 | 303.225 | 303.225 | 303.225 | 303.225 | 303.225 | 303.225 |
| `concurrency_25_clients_latency` | 100 | 0.005 | 44.656 | 109.479 | 125.126 | 131.603 | 45.413 |
| `concurrency_25_clients_throughput_rps` | 100 | 362.470 | 362.470 | 362.470 | 362.470 | 362.470 | 362.470 |
