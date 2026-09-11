# TACP Phase 2 Master Test Plan & QA Architecture

**Document:** `docs/testing/PHASE-2-TEST-PLAN.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**QA Lead:** Antigravity QA & Verification Lead  
**Date:** September 11, 2026  

---

## 1. Quality Philosophy

Phase 2 introduces mutation, process execution, and concurrency. In this phase, testing is not merely an assertion of happy paths; it is an **adversarial verification harness designed to actively attempt to break the system**.

### Test Quality Invariants
1. **Meaningful over Superficial**: Tests must validate discrete business invariants, error codes, and state transitions. No tests may be manufactured to artificially inflate counts.
2. **Deterministic & Isolated**: Tests must not rely on external networks or unmanaged global state. Every test runs in an isolated temporary directory with ephemeral SQLite databases.
3. **Regression Freeze**: The **269 existing tests from TACP 0.1** form an inviolable baseline and must pass without regression on every run.

---

## 2. Target Test Allocation (200+ New Behavioral Tests)

Phase 2 targets approximately **210 new automated tests** distributed across 6 critical domains:

```
+-------------------------------------------------------------+-------+
| Test Category                                               | Count |
+-------------------------------------------------------------+-------+
| 1. Mutation & Path Security Tests                           |   50+ |
| 2. Command Execution & Process Security Tests               |   60+ |
| 3. Concurrency, Locking & Recovery Tests                    |   30+ |
| 4. Authorization, Identity & Policy Hierarchy Tests         |   25+ |
| 5. MCP Contract & Strict Schema Tests                       |   25+ |
| 6. Resource Limits & Governor Tests                         |   20+ |
+-------------------------------------------------------------+-------+
| Total New Phase 2 Tests Planned                             |  210+ |
| Existing Read-Only Regression Baseline                      |   269 |
+-------------------------------------------------------------+-------+
| Total Target Test Suite Size                                |  479+ |
+-------------------------------------------------------------+-------+
```

---

## 3. Test Suites & Directory Layout

```
tests/
├── unit/
│   ├── test_identity_model.py          # Principal resolution, token fingerprinting
│   ├── test_policy_hierarchy.py        # 5-tier evaluation, downward restriction
│   ├── test_risk_engine.py             # R0-R5 scoring, autonomy gating
│   ├── test_approval_engine.py         # Expiry, scope matching, consumption
│   ├── test_execution_contract.py      # Contract immutability, parameter validation
│   ├── test_atomic_writer.py           # Temp file, fsync, os.replace
│   └── test_patch_parser.py            # Unified diff validation, hunk application
├── integration/
│   ├── test_workspace_patch.py         # End-to-end patch application & dry-run
│   ├── test_concurrency_locks.py       # Shared/exclusive locks, lock reapers
│   ├── test_command_execution.py       # Safe argv invocation, env scrubbing
│   ├── test_job_lifecycle.py           # Job state transitions, cancellation
│   ├── test_recovery_checkpoints.py    # Snapshot creation, diff, restore
│   └── test_circuit_breaker.py         # 4-failure trip and resume
├── security/
│   ├── test_security_matrix_88.py      # All 88+ Phase 2 security attack cases
│   ├── test_toctou_races.py            # Simulated concurrent file modification
│   ├── test_command_injections.py      # Semicolons, pipes, backticks in argv
│   └── test_secret_brokerage.py        # Env injection and output scrubbing
└── device/
    ├── test_termux_process_signals.py  # SIGTERM / SIGKILL group handling
    └── test_termux_storage_atomic.py   # Flash storage fsync durability
```

---

## 4. Adversarial Sabotage & Mutation Testing

In accordance with Phase 2 Part LVI and LVII, test quality is verified by mutation testing and intentional failure injection:
- **Authorization Bypass Mutation**: Invert policy check (`if allowed` $\to$ `if not allowed`); verify security suite immediately fails.
- **Path Jail Mutation**: Remove `startswith(workspace_root)` check; verify path traversal suite immediately catches the defect.
- **Secret Redaction Mutation**: Disable regex redaction pattern; verify secret leakage test fails.
- **Checksum Mutation**: Bypass `base_checksum` verification in patch; verify conflict tests fail.

---

## 5. Verification Gate Integration

The `./verify` script will be expanded with Phase 2 stages:
- Stage 1: ShellCheck
- Stage 2: Ruff Format
- Stage 3: Ruff Lint
- Stage 4: Mypy Strict (including all new execution and policy models)
- Stage 5: Read-Only Regression Suite (269 tests)
- Stage 6: Phase 2 Behavioral Test Suite (210+ tests)
- Stage 7: Phase 2 Security Matrix (88+ cases)
- Stage 8: pip-audit Dependency Vulnerability Scan
