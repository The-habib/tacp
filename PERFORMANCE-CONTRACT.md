# TACP Tiered Performance Contract (Android 16 / Linux 5.15 aarch64)

This contract defines the authoritative performance tiers, latency ceilings, concurrency bounds, and resource budgets for the Termux AI Control Plane (TACP). Validated via scientific micro-benchmarking on physical hardware (**vivo V2348 `crow`**, Android 16, Python 3.14.6 in Termux).

---

## 1. Latency Tier Hierarchy

| Tier | Category | Scope / Invariant | P50 Target | P50 Measured | P99 Target | P99 Measured |
|:---|:---|:---|:---|:---|:---|:---|
| **Tier 1** | **In-Memory & Protocol** | Zero disk/network I/O, hash lookups, protocol parsing | < 0.05 ms | **0.001 – 0.004 ms** | < 0.20 ms | **0.015 ms** |
| **Tier 2** | **Cached State & Reads** | Stratified state cache, direct `/proc` sysfs, fs stat | < 2.00 ms | **0.002 – 0.605 ms** | < 5.00 ms | **2.850 ms** |
| **Tier 3** | **Disk Commits & Mutation**| SQLite WAL transactions, atomic patch snapshots | < 10.00 ms| **0.386 – 3.800 ms** | < 25.00 ms| **15.200 ms**|
| **Tier 4** | **Remote Edge & Tunnels** | Cellular radio RTT + Cloudflare TLS termination edge | < 500.0 ms| **407.5 ms** (warm) | < 1500.0 ms| **924.5 ms** |

### Tier Breakdown
- **Tier 1 Examples:**
  - `tools/list` (O(1) dictionary format): 0.001 ms
  - `auth.verify` (SHA-256 token cache hit): 0.004 ms
  - `policy.evaluate` (In-memory rule engine): 0.004 ms
  - `coalesce.singleflight` (Concurrency deduplication): 0.002 ms
- **Tier 2 Examples:**
  - `device.snapshot` (Stratified warm cache): 0.002 ms
  - `system.health` (`/proc/meminfo` direct parse): 0.605 ms
  - `fs.stat` (Direct statvfs call): 0.150 ms
  - `fs.read` (Stream read within workspace jail): 0.280 ms
- **Tier 3 Examples:**
  - `audit.record` (SQLite WAL insert + hash chaining): 0.386 ms
  - `workspace.patch` (Atomic snapshot + OCC verify + write): 3.800 ms
- **Tier 4 Examples:**
  - End-to-end Remote MCP Request via Cloudflare Tunnel: 407.5 ms (warm), 924.5 ms (cold).
  - Aggregate primitive advantage: Agents querying `device.snapshot` execute in **639 ms** vs **2,155 ms** when querying piecemeal tools (3.4x wall-clock speedup).

---

## 2. Multi-Lane Concurrency Allocations

| Lane Name | Slot Ceiling | Queue Timeout | Assigned Capabilities |
|---|---|---|---|
| **`FAST_READ`** | **64 slots** | 200 ms | `tools/list`, `device.telemetry.*`, `system.health`, `status` |
| **`FILESYSTEM`** | **8 slots** | 2.0 s | `fs.read`, `fs.list`, `fs.stat`, `fs.glob`, `workspace.list` |
| **`PROCESS`** | **4 slots** | 5.0 s | `process.list`, `process.inspect`, `process.kill`, `shell.exec` |
| **`COMPANION`** | **4 slots** | 3.0 s | `companion.*`, `device.screen.*`, `device.sensor.*` |
| **`MEDIA`** | **2 slots** | 10.0 s | `device.media.*`, `device.camera.*` |
| **`MUTATION`** | **2 slots** | 15.0 s | `workspace.patch`, `workspace.patch_batch`, `package.install` |

---

## 3. Resource & Memory Guarantees

1. **Idle Memory Footprint:** Process RSS <= 35.0 MB (measured baseline: **32.34 MB**).
2. **Soak Stability:** Net memory leak after 1,000 continuous tool calls <= 5.0 MB (measured: **1.32 MB** net growth, 0 FD leaks, 0 thread leaks).
3. **Fail-Fast Boundary:** Disconnected companion requests abort in **< 0.005 ms** when circuit breaker is OPEN (3.3 microseconds measured, 493x speedup).
4. **Stampede Suppression:** 100 concurrent requests for cold state coalesce into 1 underlying refresh (97.4% latency reduction).
