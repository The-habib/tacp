# TACP Current State Snapshot & Audit Baseline

Generated: 2026-09-26T08:24:00Z
Auditor: Principal Systems Architect & Performance Lead

---

## 1. Repository & Commit State
- **Git Branch:** `main` (tracking `origin/main`)
- **HEAD Commit:** `ee53941675da8e7b4e3b71835282b2ff43798199`
  - Subject: `docs(tunnel): add automated provisioning and operator evidence records`
- **Working Tree State:** Dirty
  - 13 modified tracked files (1,597 additions, 273 deletions)
  - 36 untracked files (containing `companion/`, `src/tacp/backends/`, `src/tacp/engine/`, `src/tacp/gateway/`, `src/tacp/remote/`, etc.)
- **Git Tags in Repo:**
  - `v0.1.0-rc.1`, `v0.2.0-rc.1`, `v0.3.0-rc.1`, `v0.3.1-rc.1`, `v0.4.0-rc.1`, `v0.4.0-rc.2`, `v0.5.0-rc.1`, `v0.5.1-rc.1`
- **Declared Version (`pyproject.toml`):** `0.4.0rc1`
- **CLI Reported Version:** `TACP v0.4.0-rc.1 (MCP 2026-07-28, mode: GOVERNED)`

---

## 2. Android & Termux Runtime Environment
- **Device Hardware:** vivo V2348 (`crow` platform)
- **OS Version:** Android 16 (API Level 36)
- **Kernel:** Linux `6.6.93-android16-9-00021-g8ebca2eb142b-ab13524674` (`aarch64`)
- **Runtime:** Python 3.14.6 in Termux virtual environment (`/data/data/com.termux/files/home/tacp/.venv`)
- **Termux Process Context:** UID 10316, GID 10316
- **Termux Prefix:** `/data/data/com.termux/files/usr`

---

## 3. Tool, Capability & Backend Metrics
- **MCP Exposed Tools (Device Control ON):** 79 tools
- **MCP Exposed Tools (Device Control OFF / Baseline):** 13 tools
- **Capabilities in Engine Registry (`tacp.engine.registry`):** 68 capabilities
- **Capabilities in Legacy Service (`tacp.core.capability_service`):** 13 capabilities
- **Backends Probed (7 total):**
  - `termux`: Available (Local command execution in Termux environment)
  - `android_shell`: Available (`/system/bin/sh` non-root fallback)
  - `termux_api`: Unavailable (`companion_required` — Termux:API companion binary not active)
  - `shizuku`: Unavailable (Requires wireless debugging / Shizuku runner)
  - `root`: Unavailable (`root_required` — device unrooted)
  - `adb`: Unavailable (`unavailable` — TCP ADB port 5555 closed)
  - `android_bridge`: Unavailable (`companion_required` — internal companion APK not bound)
- **Active Backend Tiers:**
  - Tier 1 (User / Local Shell): 53 capabilities operational
  - Tier 2 (Companion API): 11 capabilities guarded / fallback
  - Tier 3/4 (Privileged ADB / Shizuku / Root): 4 capabilities strictly blocked

---

## 4. MCP Protocol & Transports
- **Protocol Versions Supported:** `2026-07-28` (modern), `2024-11-05` (legacy fallback)
- **Transports Implemented:**
  1. `stdio`: Standard input/output JSON-RPC 2.0 loop (`tacp serve`)
  2. `streamable-http`: HTTP POST `/mcp` with streaming SSE and JSON-RPC (`tacp serve-http`)
- **Remote Providers:**
  - `cloudflare`: Outbound edge tunnel (live at `https://visiting-literally-researcher-mississippi.trycloudflare.com/mcp`)
  - `direct`: Local / LAN port binding
  - `relay`: Remote proxy gateway bridge

---

## 5. Dependencies & Architecture
- **Runtime Dependencies:** Zero external pip packages (`dependencies = []`). Implemented entirely with Python 3.14 standard library (`urllib`, `sqlite3`, `http.server`, `hashlib`, `socket`, `subprocess`).
- **Development Dependencies:** `pytest`, `pytest-cov`, `ruff`, `mypy`, `pip-audit`.
- **Test Suite Volume:** 785 automated unit and integration tests passing in 59.89s.

---

## 6. Live Runtime Processes
- **Local MCP HTTP Daemon:** PID 5847 (`python -m tacp.cli.main serve-http --host 127.0.0.1 --port 8765 --auth --device-control`)
- **Cloudflare Edge Tunnel:** PID 5878 (`cloudflared tunnel --url http://127.0.0.1:8765 --no-autoupdate --edge-ip-version 4`)
- **SQLite Database:** `~/.tacp/tacp.db` (WAL mode enabled, size ~290 KB, SHM/WAL active)

---

## 7. Critical Discrepancies & Architectural Debt Identified

1. **Version Divergence:**
   - Git tags include `v0.5.1-rc.1`, but `pyproject.toml` and CLI output declare `0.4.0-rc.1`.
2. **Dual Capability System Splintering:**
   - Two competing capability engines exist:
     - `tacp.core.capability_service` (13 legacy capabilities, tied to leases and policy approval)
     - `tacp.engine.registry` (68 new capabilities, tied to backend routing)
   - CLI commands like `tacp remote status` and `tacp doctor` call the legacy service and report "13 capabilities loaded" even when device control is active with 79 tools!
3. **Uncached Backend Probing in Tool Invocations:**
   - Every `list_capabilities()` call performs sequential backend availability checks (checking filesystem binaries, environment variables, socket timeouts). This incurs high latency when scanning tools.
4. **Heavyweight Execution on Read-Only Paths:**
   - Trivial read-only operations (e.g. `system.inspect`, `device.info`, `fs.stat`) go through audit chain insertion, database WAL commit, token hash lookup, and full policy engine evaluation with identical overhead as mutating operations.
5. **Database Connection Re-creation:**
   - Several services re-instantiate `Database(cfg.db_path)` and run SQLite connections and PRAGMA setups per request rather than reusing connection pools.
6. **Uncommitted Working State:**
   - Over 49 files of core device-control and remote integration code are uncommitted in git, leaving the repository in an unversioned transition state.
