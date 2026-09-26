# Benchmark Suite: benchmark_database
- **Timestamp:** 2026-09-26T08:49:45Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 469.09 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `db_connection_open_close` | 30 | 0.510 | 0.708 | 1.037 | 1.054 | 1.087 | 0.733 |
| `db_simple_select_query` | 100 | 0.006 | 0.006 | 0.006 | 0.008 | 0.021 | 0.006 |
| `db_audit_insert_with_hash_chain` | 50 | 0.102 | 0.150 | 0.381 | 1.876 | 281.818 | 5.836 |
| `db_audit_chain_verify_integrity` | 20 | 37.493 | 38.419 | 40.791 | 40.791 | 42.371 | 38.705 |
