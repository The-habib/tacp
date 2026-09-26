# Phase 3 Baseline Environment Snapshot

**Generation Timestamp:** 2026-09-26T12:44:40Z  
**Verification Method:** Direct execution of Linux, Android, Python, and SQLite inspection commands on physical device.

---

## 1. Version Control & Git State
- **Git Commit SHA:** `ee53941675da8e7b4e3b71835282b2ff43798199`
- **Branch:** `main` (synchronized with `origin/main`)
- **Dirty / Uncommitted Files Count:** 59 files (Phase 2 implementation, tests, and benchmarks)
- **Repo Root:** `/data/data/com.termux/files/home/tacp`

---

## 2. Host Operating System & Hardware
- **Device Model:** vivo V2348 (`crow`)
- **Manufacturer / Brand:** vivo
- **Android Version:** Android 16
- **Android API / SDK Level:** 36
- **Security Patch Level:** 2026-08-01
- **Kernel Version:** Linux 5.15 (`Android 16 #1 SMP PREEMPT Thu Jun 11 04:32:26 UTC 2026 aarch64`)
- **Architecture:** `aarch64` (64-bit ARM)
- **CPU Cores:** 8 cores (Qualcomm/MediaTek big.LITTLE architecture)
- **Termux Environment Version:** v0.118.3
- **Python Runtime:** Python 3.14.6 (Clang 21.0.0 on Android)

---

## 3. Memory & Storage Invariants
- **Total Physical RAM:** `7,480,576 kB` (~7.13 GB)
- **Available RAM:** `1,186,152 kB` (~1.13 GB)
- **Free RAM:** `122,376 kB`
- **Cached RAM:** `1,198,728 kB`
- **TACP Process Baseline RSS:** `17.22 MB` (idle script), `46.2 MB` (HTTP server with warmed caches)
- **Primary Mount Point:** `/data/data/com.termux/files/home` (ext4/f2fs internal storage)
- **Total Storage Capacity:** 102.72 GB
- **Free Storage Available:** 5.21 GB

---

## 4. TACP & SQLite Configuration
- **Application Directory:** `/data/data/com.termux/files/home/.tacp`
- **Database File:** `/data/data/com.termux/files/home/.tacp/tacp.db`
- **SQLite Journal Mode:** `wal` (Write-Ahead Logging enabled)
- **SQLite Synchronous Mode:** `NORMAL` (set at connection pool creation; raw file default 2/FULL)
- **SQLite Connection Timeout:** 30.0s (`PRAGMA busy_timeout = 30000`)
- **Thread Model:** Thread-local connections via `threading.local()` in `Database`
- **TACP Version:** `0.4.0-rc.1`
- **Trust Profile:** `BALANCED`
- **Global Concurrency Ceiling:** 32 concurrent HTTP requests via `BoundedSemaphore(32)`
- **Companion IPC Configuration:** `HttpCompanionTransport` on `127.0.0.1:8766` with persistent keep-alive connection reuse and 10MB bounds
- **Remote Endpoint:** `https://men-favors-counting-packed.trycloudflare.com/mcp` (Cloudflare Tunnel)

---

## 5. Discrepancy & Reality Analysis
- The baseline reproduction in Phase 1 recorded 469 MB RSS during a memory-intensive pytest session with hundreds of compiled modules loaded; the real idle TACP server process consumes **~46 MB RSS**.
- SQLite WAL mode is confirmed active across all database sessions.
- Physical storage has 5.21 GB free; system health margin checks properly flag when remaining storage drops below safety thresholds.
