# TACP Performance Contract

## 1. Scope & Purpose
This document establishes authoritative performance budgets, concurrency ceilings, memory constraints, and latency contracts for the Termux AI Control Plane (TACP). Every new feature, provider, capability, and transport optimization merged into TACP must strictly adhere to and be evaluated against this contract.

---

## 2. Latency Budgets (Measured on Physical Hardware: aarch64, Android 16)

| Operation | Metric | Target Budget | Hard Ceilings | Invariant Rationale |
|:---|:---|:---|:---|:---|
| **MCP Dispatch (`tools/list`)** | Warm P50 | < 0.05 ms | 0.50 ms | Zero-copy dictionary serialization; cached tool definitions |
| **Capability Resolution** | Single lookup | < 0.01 ms | 0.05 ms | O(1) hash map lookup; no dynamic reflection or linear scans |
| **Policy Evaluation** | R0/R1 request | < 0.02 ms | 0.10 ms | In-memory rule check; zero disk or network I/O |
| **Device Snapshot (`device.snapshot`)** | Warm P50 | < 2.0 ms | 5.0 ms | Stratified TTL memory cache; zero subprocess fork-execs on hot path |
| **System Health (`system.health`)** | Warm P50 | < 1.0 ms | 2.5 ms | Direct `/proc` memory & storage margin checks |
| **Filesystem Listing (`fs.list`)** | Dir <= 100 items | < 3.0 ms | 10.0 ms | Single `scandir` pass with stat batching |
| **Filesystem Read (`fs.read`)** | File <= 64 KB | < 1.0 ms | 3.0 ms | Direct stream read within jail containment |
| **Token Authentication** | Cached token | < 0.02 ms | 0.10 ms | SHA-256 hash cache with generation-based invalidation |
| **Cryptographic Audit Hash** | Single record | < 0.02 ms | 0.05 ms | Canonical JSON + SHA-256 hash chaining |
| **SQLite Audit Record** | Sequential append | < 1.0 ms | 3.0 ms | WAL mode; `PRAGMA synchronous = NORMAL` |
| **Companion Probe** | Cached status | < 0.05 ms | 0.20 ms | In-memory availability flag with 30s probe interval |
| **Local End-to-End HTTP MCP** | Warm tool call | < 10.0 ms | 25.0 ms | HTTP/1.1 keep-alive loopback transport |

---

## 3. Concurrency & Throughput Limits
 
1. **Multi-Lane Admission Control:** Concurrency is partitioned across 6 isolated resource lanes:
   - `FAST_READ`: 64 slots, 200ms timeout (telemetry, info, cached state)
   - `FILESYSTEM`: 8 slots, 2.0s timeout (file read/write/stat/search)
   - `PROCESS`: 4 slots, 5.0s timeout (process execution and inspection)
   - `COMPANION`: 4 slots, 3.0s timeout (companion APK IPC and screen capture)
   - `MEDIA`: 2 slots, 10.0s timeout (camera, audio recording)
   - `MUTATION`: 2 slots, 15.0s timeout (workspace patches, batch modifications)
2. **Backpressure & Fair Queueing:** When an individual lane saturates its slot capacity and queue timeout, requests reject immediately with HTTP 503 (`RESOURCE_EXHAUSTED`) and `Retry-After: 1`. Fast read telemetry requests are guaranteed never to starve behind slow mutations or companion timeouts.
3. **Audit Group Commit:** Concurrent audit records drain via cooperative immediate transactions, preserving sequential cryptographic hash integrity while scaling past 1,000 ops/sec.
4. **Target Throughput:**
   - Pure Read-Only MCP requests: >= 8,000 req/sec (warm).
   - Audited State Tool calls: >= 500 req/sec (warm).

---

## 4. Memory Budgets & Footprint

1. **Baseline Idle Process RSS:** <= 40 MB.
2. **Peak Under 50 Concurrent Clients:** <= 75 MB.
3. **Hard Ceiling (OOM Defense):** <= 128 MB.
4. **Max Request Body Size:** 10 MB (HTTP 413 Payload Too Large enforced).
5. **Max Response Payload Size:** 10 MB (streaming or chunked truncation beyond threshold).
6. **Audit In-Memory Cache:** Bounded to the latest entry hash and 50 recent records in memory; historical records remain in SQLite.

---

## 5. Subprocess Execution & Android IPC Rules

1. **Zero Subprocess Hot Paths:** No tool execution on a warm path may invoke `/system/bin` or Termux subprocesses (`pm`, `ps`, `getenforce`, `su`) if the data can be sourced from `/proc`, `/sys`, or cached with stratified TTLs.
2. **Binary Process Isolation:** All commanded subprocess executions (`execution.request`) must use `setsid` session groups, strict argument arrays (no shell interpretation), pipe watchdogs, and bounded I/O caps.
3. **Companion Channel:** Local communication to companion APKs must use persistent connection reuse (`CompanionTransport`) to eliminate repetitive TCP handshake overhead.

---

## 6. Timeouts Architecture

- **MCP Request Timeout:** 15.0 seconds.
- **Provider Subprocess Timeout:** 30.0 seconds.
- **Companion IPC Timeout:** 10.0 seconds.
- **Database Busy Timeout:** 30.0 seconds.
- **Network Probe Timeout:** 1.0 second.
