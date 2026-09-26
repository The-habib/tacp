# TACP Phase 3 Documentation Drift Audit

**Date:** 2026-09-26  
**Auditor:** Independent Acceptance & Adversarial Testing Agent  
**Subject:** Termux AI Control Plane (TACP) v0.4.0-rc.1  
**Target Repository:** `/data/data/com.termux/files/home/tacp`

---

## Executive Summary

This audit compares the commitments made in project documentation, architecture specifications, and performance contracts against the actual source code and live runtime behavior observed on the physical test environment (vivo V2348, Android 16).

A total of **7 documentation drift defects** were identified across concurrency models, soak test durations, latency qualifications, tool parameter schemas, and credential guidance.

---

## Detailed Drift Inventory

### 1. Concurrency Model: Monolithic 32 Slots vs Multi-Lane Partitioning
* **Documented Claim:** In [docs/PERFORMANCE-CONTRACT.md](file:///data/data/com.termux/files/home/tacp/docs/PERFORMANCE-CONTRACT.md) Section 3, the concurrency model is defined as:  
  `Monolithic Max 32 concurrent requests per process`.
* **Actual Source Implementation:** In [src/tacp/core/admission.py](file:///data/data/com.termux/files/home/tacp/src/tacp/core/admission.py#L42-L50), TACP implements a multi-lane admission controller with isolated pools:
  - `FAST_READ`: 64 slots, 200ms timeout
  - `FILESYSTEM`: 8 slots, 2.0s timeout
  - `PROCESS`: 4 slots, 5.0s timeout
  - `COMPANION`: 4 slots, 3.0s timeout
  - `MEDIA`: 2 slots, 10.0s timeout
  - `MUTATION`: 2 slots, 15.0s timeout
* **Runtime Behavior:** Concurrency attacks confirmed that fast read requests acquire slots from the 64-slot pool and are completely unblocked by saturated mutation slots (0.016 ms acquisition under saturation).
* **Severity:** P3 (Documentation lag behind architectural advancement).
* **Remediation:** Update `PERFORMANCE-CONTRACT.md` and `02-ARCHITECTURE.md` to document the 6-lane admission model and its slot allocations.

---

### 2. Soak Test Duration: 30 Minutes Claimed vs 1.07 Seconds Executed
* **Documented Claim:** [docs/07-TEST-STRATEGY.md](file:///data/data/com.termux/files/home/tacp/docs/07-TEST-STRATEGY.md) and Phase 3 summary reports state that a "sustained soak test was executed to prove zero memory and file descriptor leakage."
* **Actual Source & Artifact:** In `artifacts/phase3/soak_test_report.json`, the recorded test parameters are:
  - `total_cycles`: 1000 requests
  - `duration_seconds`: **1.07 seconds** (throughput: 930.8 req/sec)
* **Runtime Behavior:** The soak test script was an un-paced in-memory loop rather than a 30- to 60-minute continuous wall-clock endurance run.
* **Severity:** P2 (Misleading empirical qualification).
* **Remediation:** Update documentation to distinguish between "1,000-cycle high-throughput burst test" and "30-minute endurance soak test."

---

### 3. Microsecond Latency Metric Attribution
* **Documented Claim:** Summaries cite latencies of `0.545 µs` (tracer), `0.0033 ms` (circuit breaker), and `0.0038 ms` (state cache) alongside end-to-end operation tables.
* **Actual Source & Instrumentation:** 
  - `0.545 µs` measures an in-process noop context manager `tracer.span("noop")` where timer overhead (`time.perf_counter_ns` @ 268 ns) accounts for ~49% of the duration.
  - `0.0033 ms` measures an in-process boolean check in `CircuitBreaker.allow_request()`.
  - `0.0038 ms` measures an in-process dictionary retrieval in `DeviceStateManager._get_cached()`.
* **Runtime Behavior:** Real end-to-end MCP HTTP requests take between 17 ms and 100 ms depending on payload serialization and network loopback.
* **Severity:** P3 (Clarity & measurement qualification).
* **Remediation:** Explicitly partition performance tables into "Internal In-Memory Microbenchmarks" vs "Real MCP HTTP End-to-End Latency".

---

### 4. Filesystem Tool Parameter Schema: `path` vs `subpath`
* **Documented Claim:** Examples in [docs/client-examples.md](file:///data/data/com.termux/files/home/tacp/docs/client-examples.md) and [docs/remote-mcp.md](file:///data/data/com.termux/files/home/tacp/docs/remote-mcp.md) illustrate file read calls using:
  `{"name": "fs.read", "arguments": {"workspace_id": "...", "path": "file.txt"}}`
* **Actual Source Implementation:** In [src/tacp/access/mcp/tools.py](file:///data/data/com.termux/files/home/tacp/src/tacp/access/mcp/tools.py), the schema explicitly defines:
  `required: ["workspace_id", "subpath"]`
* **Runtime Behavior:** Calling `fs.read` with `path` results in an MCP error: `Error: Missing required parameters: workspace_id and subpath`.
* **Severity:** P3 (Client integration friction).
* **Remediation:** Either accept `path` as an alias for `subpath` in `fs.read` or align all documentation and examples to use `subpath`.

---

### 5. Registered Tool Count Discrepancy
* **Documented Claim:** Previous Phase 2 and early Phase 3 reports claim "72 tools" or "78 tools".
* **Actual Source & Runtime:** Live MCP `tools/list` returns **82 registered tools** when device control, system, filesystem, process, and remote tools are active.
* **Severity:** P3 (Documentation freshness).
* **Remediation:** Synchronize documentation tables to reflect the current 82-tool registry.

---

### 6. Bearer Token Secret Masking Guidance vs Generated Files
* **Documented Claim:** [docs/SECRET-HANDLING.md](file:///data/data/com.termux/files/home/tacp/docs/SECRET-HANDLING.md) mandates that all tokens must be redacted and never committed in plaintext.
* **Actual Runtime Behavior:** Deployment scripts wrote live, unmasked bearer tokens to `TACP_CLIENT_CONFIGS.md` and `TACP_AGENT_CONNECT_PROMPT.txt` in the root workspace directory.
* **Severity:** P2 (Credential exposure risk).
* **Remediation:** Modify generator scripts to apply `chmod 600` and encourage passing tokens via environment variables rather than persisting plaintext tokens into markdown files.

---

### 7. Battery Telemetry Availability on Android 16
* **Documented Claim:** [docs/11-DEVICE-VALIDATION.md](file:///data/data/com.termux/files/home/tacp/docs/11-DEVICE-VALIDATION.md) states that battery percentage, charging status, and temperature are probed via `/sys/class/power_supply/battery`.
* **Actual Runtime Behavior:** On Android 16 (API 36) in an unprivileged Termux context (`untrusted_app_27`), SELinux blocks access to sysfs battery nodes (`open failed: Permission denied`). TACP falls back to negative-cached default values (`{"percentage": 100, "status": "unknown"}`).
* **Severity:** P3 (Hardware compatibility note).
* **Remediation:** Document in `11-DEVICE-VALIDATION.md` and `12-COMPATIBILITY-MATRIX.md` that Android 16 enforces strict sysfs isolation, requiring Termux:API companion app for live battery telemetry.
