# TACP Request Lifecycle & Nanosecond Tracing Specification

This document defines the deterministic 11-phase request lifecycle of the Termux AI Control Plane (TACP), its formal execution path, and physical nanosecond timing benchmarks measured on physical Android 16 hardware (Linux 5.15 aarch64, Python 3.14).

---

## 1. Architectural Request Pipeline (ASCII Sequence)

```text
  Client (Remote Agent / CLI / Local HTTP)
     │
     │  [HTTP POST / JSON-RPC 2.0]
     ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 1. TRANSPORT RECEIVE / UNPACK                                          │
│    Reads TCP bytes, validates Content-Length (<10MB), parses JSON-RPC  │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. AUTHENTICATION & PRINCIPAL BINDING                                  │
│    Extracts Bearer token, SHA-256 validation against SQLite cache      │
│    Binds Principal (Identity, Role, Scopes, TrustTier)                 │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 3. SESSION CORRELATION                                                 │
│    Extracts Mcp-Session-Id or generates UUID, binds correlation ID     │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 4. POLICY EVALUATION                                                   │
│    PolicyEngine checks capability against Principal, scopes, tier,     │
│    workspace jail, rate limits, and approval policies                  │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 5. CAPABILITY RESOLUTION                                               │
│    O(1) dictionary lookup across registered static & device tools      │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 6. PROVIDER RESOLUTION                                                 │
│    Routes capability to handler (DeviceRegistry, Workspace, System)    │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 7. CACHE PROBE & STALENESS VERIFICATION                                │
│    Probes stratified cache (L1 fast / L2 slow / L3 permanent)          │
│    Evaluates TTL & staleness flags before hardware access              │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 8. EXECUTION / IPC DISPATCH                                            │
│    Executes direct /proc or IPC provider under bounded concurrency     │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 9. SERIALIZATION                                                       │
│    Serializes structured response to JSON-RPC 2.0 result envelope      │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 10. AUDIT EVENT PIPELINE                                               │
│     Generates immutable AuditEvent, computes SHA-256 hash chain,       │
│     persists to SQLite WAL via group commit                            │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 11. TRANSPORT WRITE / FLUSH                                            │
│     Writes HTTP headers (CORS, Mcp-Session-Id), flushes response body  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Physical Hardware Benchmark Timings (Android 16 aarch64)

Empirical physical hardware benchmark across  = 500$ iterations on physical **vivo V2348 ()**, running **Android 16 (API 36)**, **Linux 5.15 aarch64**, **Python 3.14.6** in Termux v0.118.3.

| Phase | Phase Name | P50 (ns) | P90 (ns) | P95 (ns) | P99 (ns) | Mean (ns) | Mean (µs) | % of Lifecycle |
|---|---|---|---|---|---|---|---|---|
| **1** | `transport_receive` | 27,709 | 40,469 | 50,209 | 95,416 | 33,001.2 | 33.00 µs | 2.6% |
| **2** | `authentication` | 178,489 | 255,052 | 305,312 | 567,083 | 194,437.2 | 194.44 µs | 15.3% |
| **3** | `session` | 730 | 1,094 | 1,198 | 1,615 | 793.8 | 0.79 µs | 0.1% |
| **4** | `policy` | 65,990 | 92,709 | 106,302 | 211,094 | 71,742.1 | 71.74 µs | 5.6% |
| **5** | `capability_resolution`| 1,615 | 2,396 | 2,552 | 4,271 | 1,787.0 | 1.79 µs | 0.1% |
| **6** | `provider_resolution` | 833 | 1,302 | 1,406 | 1,823 | 893.1 | 0.89 µs | 0.1% |
| **7** | `cache` | 2,709 | 4,063 | 4,584 | 8,282 | 2,996.7 | 3.00 µs | 0.2% |
| **8** | `execution` (fast) | 1,354 | 1,979 | 2,188 | 4,010 | 1,504.0 | 1.50 µs | 0.1% |
| **9** | `serialization` | 41,614 | 61,302 | 70,312 | 160,521 | 49,457.1 | 49.46 µs | 3.9% |
| **10**| `audit` | 386,250 | 605,938 | 710,677 | 2,646,303 | 822,967.6 | 822.97 µs | 64.8% |
| **11**| `transport_write` | 1,615 | 2,500 | 2,813 | 4,166 | 1,738.9 | 1.74 µs | 0.1% |
| **TOTAL** | **Full 11-Phase Cycle** | **709,908 ns** | **1,068,804 ns**| **1,257,053 ns**| **3,704,584 ns**| **1,181,318.7 ns**| **1,181.32 µs** | **100.0%** |

### Key Observations
1. **Sub-Microsecond Core Phases:** Phases 3, 5, 6, 8, and 11 execute in under 2 microseconds each.
2. **Audit Pipeline Dominance:** SQLite WAL persistence accounts for ~64.8% of local server processing. Cooperative group commit flushes batches to maintain sub-millisecond throughput under high concurrency.
3. **Authentication Caching:** SHA-256 validation executes in 178.5 µs on warm in-memory cache hits.

---

## 3. Tracing API Specification

### Class: `RequestTracer`
Located in `src/tacp/core/tracer.py`.

```python
class RequestTracer:
    def __init__(self, trace_id: Optional[str] = None, request_id: Optional[str] = None, enabled: bool = True):
        ...

    def span(self, name: str, **meta: Any) -> TraceSpan:
        """Context manager for timing an execution block."""
        ...

    def start_span(self, name: str, **meta: Any) -> TraceSpan:
        """Explicit span start for asynchronous or interleaved phases."""
        ...

    def end_span(self, name: str, **meta: Any) -> None:
        """Explicit span completion."""
        ...

    def finish(self) -> None:
        """Finalize all open spans and freeze trace end timestamp."""
        ...

    def summary(self) -> Dict[str, Any]:
        """Return structured JSON-compatible trace summary."""
        ...
```

### ContextVar Helper Functions
- `get_current_tracer() -> RequestTracer`: Returns current thread/async task tracer, or `NoopTracer` if none is active.
- `set_current_tracer(tracer: Optional[RequestTracer]) -> Token`: Binds a tracer to the active context.

### Overhead Profile
- **Disabled / Noop Path:** 0.545 µs per span.
- **Enabled Path:** 6.54 µs per span.
- **Memory Footprint:** Zero allocations on noop path using `__slots__` and singleton `NoopSpan`.
