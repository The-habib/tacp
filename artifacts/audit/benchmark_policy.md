# Benchmark Suite: benchmark_policy
- **Timestamp:** 2026-09-26T11:00:40Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 469.09 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `policy_evaluate_read_only` | 100 | 0.003 | 0.003 | 0.003 | 0.004 | 0.004 | 0.003 |
| `policy_evaluate_mutation_denied` | 100 | 0.003 | 0.003 | 0.004 | 0.004 | 0.004 | 0.003 |
| `token_verify_hash_and_db` | 50 | 0.003 | 0.003 | 0.003 | 0.003 | 0.004 | 0.003 |
