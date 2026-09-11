# Phase 2 — Vertical Slice 1: Performance Benchmark Report

**Device:** Android Host running Termux  
**Python Runtime:** Python 3.14.6  
**Storage:** Internal Flash (UFS) / ext4

---

## 1. Empirical Latency Measurements

Benchmarks were collected on live Android hardware using real SQLite databases, real snapshot generation, and physical disk persistence (`fsync`):

| Operation | Iterations | Mean Latency | p95 Latency | Notes |
| :--- | :---: | :---: | :---: | :--- |
| **Dry-Run Simulation** | 50 | **2.33 ms** | **3.10 ms** | In-memory diff parsing & hunk matching; 0 disk mutations |
| **Governed Live Patch** | 20 | **34.70 ms** | **221.58 ms** | Full 16-stage pipeline: OCC, lock, approval consumption, snapshot, `fsync`, atomic rename, audit logging |
| **Rollback Execution** | 1 | **3.35 ms** | **3.35 ms** | Snapshot restore with OCC check & atomic replace |

---

## 2. Test Suite Throughput

- **Total Test Count:** 356 automated tests
- **Total Execution Duration:** 22.65 seconds
- **Mean Test Latency:** 63.6 ms per test (includes end-to-end integration and security attack suites)
- **Memory Footprint:** Resident Set Size (RSS) under 65 MB throughout full test execution.

---

## 3. Scalability Analysis

- In-memory hunk processing scales linearly with the size of the diff ((N)$ where  \le 256	ext{ KB}$).
- Database operations (locking, approvals, audit logging) execute against indexed tables, preventing sequential table scans as the audit log grows.
