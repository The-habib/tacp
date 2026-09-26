# Benchmark Suite: benchmark_mcp
- **Timestamp:** 2026-09-26T11:00:33Z
- **Platform:** Android-16-aarch64-64bit
- **Python:** 3.14.6
- **Base RSS:** 469.09 MB

| Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |
|---|---|---|---|---|---|---|---|
| `mcp_server_factory_creation` | 20 | 0.936 | 1.800 | 2.175 | 2.175 | 2.261 | 1.824 |
| `mcp_initialize_handshake` | 100 | 0.002 | 0.002 | 0.003 | 0.004 | 0.004 | 0.002 |
| `mcp_tools_list_dispatch` | 50 | 0.002 | 0.002 | 0.002 | 0.002 | 0.003 | 0.002 |
| `mcp_resources_list_dispatch` | 50 | 0.003 | 0.003 | 0.003 | 0.003 | 0.005 | 0.003 |
| `mcp_prompts_list_dispatch` | 50 | 0.002 | 0.002 | 0.002 | 0.003 | 0.004 | 0.002 |
| `mcp_tools_list_serialization` | 100 | 0.249 | 0.255 | 0.302 | 0.327 | 0.996 | 0.269 |
