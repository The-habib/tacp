# TACP Independent Acceptance Test: Baseline Test Environment

This document establishes the verified runtime test subject, physical hardware inventory, git state, software environment, and discrepancy audit between documentation, source code, and live runtime behavior.

---

## 1. Physical Hardware & Operating System Inventory

| Parameter | Authoritative Value Measured at Runtime | Verification Command / Source |
|:---|:---|:---|
| **Device Model** | vivo V2348 (`crow`) | `getprop ro.product.model`, `getprop ro.product.device` |
| **Manufacturer & Brand** | vivo / vivo | `getprop ro.product.manufacturer`, `ro.product.brand` |
| **Android OS Version** | Android 16 (API Level 36) | `getprop ro.build.version.release`, `ro.build.version.sdk` |
| **Linux Kernel** | `5.15.197-android13-8-00049-g7d37760ec777-ab15613975 #1 SMP PREEMPT Thu Jun 11 04:32:26 UTC 2026 aarch64` | `uname -a` |
| **CPU Architecture** | ARM64 (`aarch64`), 8-core Big.LITTLE | `/proc/cpuinfo` |
| **Total Physical RAM** | 7,480,576 kB (7.13 GB / 7.48 GB gross) | `/proc/meminfo` (`MemTotal`) |
| **Available RAM** | 974,628 kB (~952 MB available) | `/proc/meminfo` (`MemAvailable`) |
| **Data Partition Storage** | 103 GB total, 97 GB used, 5.1 GB available (95% full) | `df -h /data` |
| **SELinux Mode** | Enforcing (untrusted_app context: `u:r:untrusted_app_27:s0:c60,c257,c512,c768`) | `id -Z` |

---

## 2. Software & Runtime Stack

| Component | Measured State / Version | Source |
|:---|:---|:---|
| **Python Runtime** | Python 3.14.6 (CPython, aarch64) | `python3 --version` |
| **Virtual Environment** | `/data/data/com.termux/files/home/tacp/.venv` | Active virtualenv path |
| **Termux Tools** | `termux-tools 1.46.0+really1.45.0-1` | `dpkg -l termux-tools` |
| **Termux API Package** | `termux-api 0.60.0` (CLI utilities present; companion APK unlinked) | `dpkg -l termux-api` |
| **Cloudflare Tunnel Daemon** | `cloudflared` (Active, PID 5878, PID 6720) | `ps aux | grep cloudflared` |
| **Active Tunnel URL** | `https://men-favors-counting-packed.trycloudflare.com` | `~/.tacp/remote.json` |
| **TACP HTTP Server** | Listening on `127.0.0.1:8765`, PID 6706 (`serve-http --auth --device-control`) | `ps aux`, `~/.tacp/tacp-http.pid` |
| **SQLite Engine** | SQLite 3 with WAL enabled, `synchronous = NORMAL`, `busy_timeout = 30000` | `src/tacp/infrastructure/database.py` |
| **TACP Software Version** | `0.4.0-rc.1` (pyproject: `0.4.0rc1`) | `tacp version`, `pyproject.toml` |
| **MCP Protocol Support** | Modern `2026-07-28`, with fallback negotiation for `2024-11-05`, `2025-03-20`, `2025-11-25` | `src/tacp/access/mcp/protocol.py` |

---

## 3. Git Repository & Working Tree Status

- **Repository Root:** `/data/data/com.termux/files/home/tacp`
- **Active Branch:** `main`
- **Head Commit:** `ee53941675da8e7b4e3b71835282b2ff43798199`
- **Working Tree:** Dirty with Phase 3 code implementations and benchmark suites:
  - Modified tracked files: `src/tacp/access/mcp/server.py`, `src/tacp/access/mcp/tools.py`, `src/tacp/cli/main.py`, `src/tacp/control/identity.py`, `src/tacp/core/audit_service.py`, `src/tacp/core/patch_service.py`, `src/tacp/domain/errors.py`.
  - Untracked Phase 3 modules: `src/tacp/core/admission.py`, `src/tacp/core/coalesce.py`, `src/tacp/core/idempotency.py`, `src/tacp/core/lifecycle.py`, `src/tacp/core/state.py`, `src/tacp/core/tracer.py`.
  - Test suites: `tests/chaos/`, `tests/security/test_redteam.py`, `tests/security/test_audit_tamper_advanced.py`, `tests/unit/test_admission.py`, `tests/unit/test_cancellation.py`, `tests/unit/test_coalesce.py`, `tests/unit/test_companion_circuit_breaker.py`, `tests/unit/test_idempotency.py`, `tests/unit/test_tools_list_pagination.py`, `tests/unit/test_tracer.py`.

---

## 4. Documentation vs. Source Code vs. Runtime Discrepancy Matrix

| Feature / Metric | Legacy Documentation (`docs/`) | Phase 3 Contract / Report | Actual Source Implementation | Live Runtime Behavior | Discrepancy Identified |
|---|---|---|---|---|---|
| **Concurrency Model** | "Max 32 concurrent requests per process" (`docs/PERFORMANCE-CONTRACT.md`) | Multi-lane resource isolation: `FAST_READ` (64), `FILESYSTEM` (8), `MUTATION` (2) | `AdmissionController` in `src/tacp/core/admission.py` enforces 6 lanes | Requests acquire lane semaphores per capability | **Documentation Drift:** Legacy `docs/` still refers to monolithic 32-slot semaphore. |
| **Cache Stampede** | Not documented in `docs/` | `SingleFlight` group coalesces concurrent snapshot requests | `SingleFlight.do()` in `src/tacp/core/coalesce.py` | 100 concurrent requests execute 6 underlying runs | **Match:** Phase 3 implementation verified in runtime. |
| **Companion Timeout** | 10.0s hardcoded timeout | Circuit breaker trips to OPEN, fails fast in 3.3 µs | `HttpCompanionTransport` in `src/tacp/backends/companion_transport.py` | Closed port 59998 fails fast in 3.3 µs | **Match:** Circuit breaker verified in runtime. |
| **Audit Verification** | Boolean pass/fail | Exact sequence # and row ID pinpointing | `AuditService.verify_chain_detailed()` in `src/tacp/core/audit_service.py` | `tacp audit verify` CLI output prints exact sequence and row ID | **Match:** Detailed forensics verified in runtime. |
| **`tools/list` Optimization**| Unpaginated static list | Paginated with `cursor`, `limit`, and `category` | Handled in `server.py` lines 122–160 | Client query `limit=5` returns 5 tools and `nextCursor` | **Match:** Implemented and operational. |
