# Benchmark Suite: benchmark_database
- **Timestamp:** 2026-09-26T11:00:41Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 469.09 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `db_connection_open_close` | 30 | 0.481 | 1.044 | 1.496 | 1.546 | 1.747 | 1.030 |
| `db_simple_select_query` | 100 | 0.005 | 0.005 | 0.006 | 0.007 | 0.007 | 0.005 |
| `db_audit_insert_with_hash_chain` | 50 | 0.097 | 0.115 | 0.154 | 0.173 | 0.205 | 0.122 |
| `db_audit_chain_verify_integrity` | 20 | 50.423 | 51.258 | 53.466 | 53.466 | 55.833 | 51.615 |
