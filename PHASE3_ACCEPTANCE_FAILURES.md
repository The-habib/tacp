# TACP Phase 3 Acceptance Failures & Defect Inventory

**Date:** 2026-09-26  
**Auditor:** Independent Acceptance & Adversarial Testing Agent  
**Status:** Diagnostic Failure Log (Prior to Remediation)

---

## Defect Summary Matrix

| ID | Issue | Severity | Component | Reproduction Command |
|:---|:---|:---:|:---|:---|
| **DEF-01** | Flaky Unit Test in `test_coalesce.py` (`assert 2 == 1`) | **P2** | `tests/unit/test_coalesce.py` | `.venv/bin/pytest tests/unit/test_coalesce.py` (15% flake rate) |
| **DEF-02** | Historical Production Database Audit Hash Corruption (#1272) | **P2** | Production SQLite DB (`tacp.db`) | `.venv/bin/tacp audit verify` |
| **DEF-03** | Plaintext Bearer Tokens Persisted in User Configuration Docs | **P2** | CLI Setup & Documentation | `grep -rn "tacp_sec_" TACP_CLIENT_CONFIGS.md docs/` |
| **DEF-04** | Soak Test Runtime Discrepancy (1.07s vs 30m) | **P3** | `benchmarks/phase3/soak_test.py` | `cat artifacts/phase3/soak_test_report.json` |

---

## Detailed Failure Reports

### DEF-01: Flaky Test in SingleFlight Coalescing Unit Test
* **Issue:** `tests/unit/test_coalesce.py::test_singleflight_coalescing` intermittently fails with `AssertionError: assert 2 == 1`.
* **Reproduction:** Running the test in a 20-iteration loop under concurrent system load produced **3 failures out of 20 runs (15% failure rate)**.
  ```bash
  python3 -c '
  import subprocess
  fails = sum(1 for _ in range(20) if subprocess.run([".venv/bin/pytest", "tests/unit/test_coalesce.py"]).returncode != 0)
  print(f"Failures: {fails}/20")
  '
  ```
* **Evidence:**
  ```text
  FAILED tests/unit/test_coalesce.py::test_singleflight_coalescing - assert 2 == 1
  assert execution_count == 1
  ```
* **Root Cause:** In [tests/unit/test_coalesce.py](file:///data/data/com.termux/files/home/tacp/tests/unit/test_coalesce.py#L22-L24), 50 tasks are submitted to `ThreadPoolExecutor(max_workers=50)` sequentially in a Python for-loop without barrier synchronization. On ARM64 Android under CPU load, the first worker thread completes its simulated work (`time.sleep(0.05)`) and cleans up the active call (`self._calls.pop(key, None)`) before the 50th worker thread is scheduled by the OS. The late thread finds no in-flight call and starts a second execution.
* **Severity:** **P2** (Test suite reliability defect; causes occasional pipeline and full-suite red status).
* **Affected Component:** `tests/unit/test_coalesce.py`.
* **Suggested Remediation:** Use `threading.Barrier(N)` inside the worker function before calling `group.do("snapshot", expensive_operation)` to ensure all threads begin single-flight entry simultaneously.

---

### DEF-02: Historical Audit Hash Corruption in Production Database
* **Issue:** Running `tacp audit verify` on the live physical database `~/.tacp/tacp.db` reports cryptographic verification failure at record sequence #1272.
* **Reproduction:**
  ```bash
  .venv/bin/tacp audit verify
  ```
* **Evidence:**
  ```text
  Verification Result: FAILED
  Corrupted Sequence:  1272
  Row ID:              1272
  Reason:              Hash pointer mismatch (tampering or broken chain)
  ```
* **Root Cause:** Sequence entry #1272 was recorded during Phase 2 rapid concurrency testing prior to the implementation of the Phase 3 transactional hash cache and write serialization locks. An unchained write occurred that broke the linear link from entry 1271 to 1272. All entries from 1273 onwards are valid, and isolated tests on clean test databases pass 100%.
* **Severity:** **P2** (Data integrity alert in historical database; does not impair runtime operations but invalidates end-to-end historical audits).
* **Affected Component:** Database `~/.tacp/tacp.db` (`audit_logs` table).
* **Suggested Remediation:** Provide a database repair or re-anchoring migration utility (`tacp audit reanchor`) that cryptographically signs a checkpoint at sequence 1272 with human operator approval.

---

### DEF-03: Plaintext Bearer Tokens Persisted in Documentation & Prompt Files
* **Issue:** Deployment and connection scripts generated markdown and text configuration files containing live, unmasked authentication tokens.
* **Reproduction:**
  ```bash
  grep -rn "tacp_sec_[0-9a-f]" TACP_CLIENT_CONFIGS.md TACP_AGENT_CONNECT_PROMPT.txt docs/
  ```
* **Evidence:**
  - `TACP_AGENT_CONNECT_PROMPT.txt`: Contains live active bearer token
  - `TACP_CLIENT_CONFIGS.md`: Contains live active bearer token in JSON configuration blocks
  - `docs/remote-mcp.md`: Contains active bearer token
  - `docs/client-examples.md`: Contains active bearer token
* **Root Cause:** The zero-touch automated setup command (`tacp setup`) automatically printed and exported ready-to-copy client configuration files containing the generated token for user convenience, without applying restrictive file permissions (`chmod 600`) or substituting placeholders.
* **Severity:** **P2** (Credential exposure risk on shared filesystems or public git pushes).
* **Affected Component:** `tacp setup` CLI export routines and documentation templates.
* **Suggested Remediation:** Update `tacp setup` to restrict output configuration files to mode `0600`, replace raw tokens in general documentation with `<TACP_AUTH_TOKEN>`, and prompt the user before writing persistent tokens to disk.

---

### DEF-04: Soak Test Runtime Discrepancy (1.07s vs 30m)
* **Issue:** The formal test strategy specifies a sustained soak test (minimum 30 minutes), but the executed benchmark was a rapid 1,000-cycle loop lasting 1.07 seconds.
* **Reproduction:**
  ```bash
  cat artifacts/phase3/soak_test_report.json | grep -E "duration|cycles"
  ```
* **Evidence:**
  ```json
  "total_cycles": 1000,
  "duration_seconds": 1.07,
  "throughput_req_per_sec": 930.81
  ```
* **Root Cause:** `benchmarks/phase3/soak_test.py` was authored as an un-paced throughput burst test rather than a time-based endurance daemon. While it successfully demonstrated zero socket and thread leaks across 1,000 rapid cycles, it did not observe thermal throttling, long-term memory garbage collection pauses, or background OS sleep cycles.
* **Severity:** **P3** (Evidence completeness).
* **Affected Component:** `benchmarks/phase3/soak_test.py`.
* **Suggested Remediation:** Implement a time-paced soak runner with `--duration-minutes 30` that paces requests at 10–20 req/sec over a sustained 30-minute interval.
