# TACP Phase 5: Current State Re-Audit Report
**Document ID:** `TACP-AUDIT-P5-001`  
**Target Baseline:** `v0.4.0-rc.1` (Commit: `a8e74f1`)  
**Evaluation Date:** 2026-09-11  
**Auditor Roles:** Architect & Security Architect  
**Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Executive Summary & Baseline Inventory

Prior to architectural modification in Phase 5, an independent audit of the repository, codebase, configuration, tests, and documentation was conducted. The baseline repository snapshot is:
- **Git Commit:** `a8e74f1`
- **Git Branch:** `main` (Clean working tree, up-to-date with `origin/main`)
- **Release Tags:** `v0.1.0-alpha.1`, `v0.2.0-rc.1`, `v0.3.0-rc.1`, `v0.3.1-rc.1`, `v0.4.0-rc.1`
- **Package Version:** `0.4.0rc1` in `pyproject.toml`, `0.4.0-rc.1` in `src/tacp/__init__.py`
- **Test Baseline:** 618 passing tests (329 unit/integration/device + 289 security) across 7 verification stages on Termux Android `aarch64` (Python 3.14.6).

---

## 2. Granular Capability & Subsystem Classification

The audit evaluates each component against strict evidence tiers:
- **IMPLEMENTED:** Logic exists in source code.
- **TESTED:** Executed under automated unit or integration tests.
- **SECURITY TESTED:** Targeted by adversarial security test cases.
- **DEVICE VERIFIED:** Validated on physical Android/Termux `aarch64` hardware.
- **ENFORCED:** Bound by cryptographic invariants, fail-closed access controls, or OS kernel primitives.
- **DOCUMENTED:** Described in project documentation or architecture specs.
- **CLAIMED BUT NOT ENFORCED:** Stated as a guarantee in docs or domain models but lacking genuine underlying enforcement.

| Subsystem / Capability | Impl | Test | SecTest | DevVer | Enforced | Doc | Claimed Not Enforced | Status / Notes |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Controlled Exec (`printf`, `echo`, `true`)** | YES | YES | YES | YES | PARTIAL | YES | NO | Enforced via allowlist, but path resolution contains substitution flaw. |
| **Arbitrary Shell Execution Denial** | YES | YES | YES | YES | YES | YES | NO | `shell=False`, no shell wrappers, strict negative API compliance. |
| **Workspace CWD Jail** | YES | YES | YES | YES | YES | YES | NO | `resolve_working_directory()` enforces `.is_relative_to()`. |
| **Process Group Containment (`killpg`)** | YES | YES | YES | YES | YES | YES | NO | Uses `start_new_session=True` and `os.killpg(pgid)`. |
| **Process Cancellation** | YES | YES | YES | YES | PARTIAL | YES | NO | Cancels by `pgid`, but lacks start-time PID reuse defense. |
| **Execution Contract Hashing** | YES | YES | YES | YES | YES | YES | NO | SHA-256 over 9 fields; requires expansion for version and digest. |
| **Audit Hash Chain** | YES | YES | YES | YES | YES | YES | NO | Tamper-evident SHA-256 hash chain with Merkle root verification. |
| **Scoped Approval Engine** | YES | YES | YES | YES | PARTIAL | YES | NO | Hashes bearer token, atomic consumption, but has magic string checks. |
| **Network Isolation** | NO | NO | NO | NO | NO | YES | **YES** | **CLAIMED BUT NOT ENFORCED**: `network_enabled: bool` exists in contract, but unrooted Termux has no network namespace enforcement! |
| **Output Flooding Protection** | YES | YES | YES | YES | PARTIAL | YES | **YES** | **PARTIAL**: Caps byte buffer, but continues reading loop (Model A) causing CPU burn DoS. |
| **Environment Variable Security** | YES | YES | YES | YES | PARTIAL | YES | **YES** | **DENYLIST FLAW**: Uses regex denylist rather than strict safe allowlist. |
| **Identity / Authority Derivation** | YES | YES | YES | YES | PARTIAL | YES | **YES** | **MAGIC STRINGS**: Checks `principal.id == "operator"` or `"human"`. |
| **Emergency Stop** | YES | YES | YES | YES | PARTIAL | YES | NO | Cancels active executions via CLI, but lacks dedicated audit & caller authority check. |
| **Crash Recovery & Reconciliation** | YES | YES | YES | YES | PARTIAL | YES | NO | Reconciles stuck RUNNING jobs, but lacks start-time process identity check. |

---

## 3. Discovered Security Vulnerabilities & Critical Findings

### Finding 1: Critical Executable Path Substitution Vulnerability (Severity: HIGH)
- **Location:** `src/tacp/core/execution_resolver.py:149-160`
- **Mechanism:** When a caller provides an explicit path containing a slash (e.g., `./printf`, `/tmp/printf`, or `<workspace>/bin/printf`), `ExecutionResolver.resolve_executable()` checks:
  1. If `candidate.exists() and candidate.is_file() and os.access(..., os.X_OK)`
  2. If `Path(clean_path).name` is in `PERMITTED_EXECUTABLE_NAMES` (`{"printf", "echo", "true"}`)
  3. If `candidate.resolve().name` is not in `FORBIDDEN_EXECUTABLE_NAMES`
- **Flaw:** It **never verified** that `candidate.resolve()` is located inside `SAFE_SEARCH_PATHS` (`/data/data/com.termux/files/usr/bin`, `/system/bin`, `/usr/bin`, `/bin`)!
- **Impact:** An unprivileged caller could create a malicious binary named `printf` in their workspace or `/tmp` and execute arbitrary binary code.
- **Remediation:** Enforce that any candidate path, whether bare or explicit, must resolve to a real canonical path strictly rooted inside a designated trusted system directory in `SAFE_SEARCH_PATHS`. Non-root paths must be rejected unconditionally.

### Finding 2: Network Isolation False Claim (Severity: MEDIUM)
- **Location:** `src/tacp/domain/contract.py`, `src/tacp/providers/process_executor.py`
- **Mechanism:** `ExecutionContract` defines `network_enabled: bool = False`, and documentation claims network containment.
- **Flaw:** On unrooted Android/Termux, `ProcessExecutor` executes `subprocess.Popen` without network namespaces, iptables, or seccomp socket filters. The child process has access to whatever network interfaces the Termux app process has.
- **Impact:** Claiming "network isolation" provides false assurance.
- **Remediation:** Eliminate false claims. Formally introduce `NETWORK_UNENFORCED`. The policy engine must reject any capability requiring network restriction unless true enforcement is present.

### Finding 3: Output Flooding CPU-Burn Denial of Service (Severity: MEDIUM)
- **Location:** `src/tacp/providers/process_executor.py:166-185`
- **Mechanism:** When a child process floods stdout/stderr beyond `max_stdout` or `max_stderr`, the buffer stops expanding (`stdout_trunc = True`), but the `select()` loop continues reading and discarding 4096-byte chunks until `timeout_seconds` (up to 60s) expires.
- **Flaw:** A process doing `yes` or an infinite output loop consumes 100% CPU on a mobile core for the full timeout duration.
- **Remediation:** Adopt **Model B**: As soon as output bytes exceed the contractual limit, immediately terminate the process group via `_kill_process_group()`, mark status `OUTPUT_LIMIT_EXCEEDED`, and exit cleanly.

### Finding 4: Magic String Identity Authority (Severity: MEDIUM)
- **Location:** `src/tacp/control/policy.py:279-281`, `src/tacp/control/approval.py:424`
- **Mechanism:** Policy checks `context.principal.role == "operator" or context.principal.id in ("operator", "human_operator")`. Approval check uses `if ticket.principal_id not in (principal_id, "human", "all")`.
- **Flaw:** Authority is conferred by identity strings rather than cryptographic credentials, roles, or formal `Authority` grants.
- **Remediation:** Implement a formal `Authority` model where privilege derives strictly from `Role`, `TrustTier`, and explicit capability grants. Magic name strings are prohibited.

### Finding 5: Environment Variable Denylist Flaw (Severity: MEDIUM)
- **Location:** `src/tacp/core/execution_resolver.py:311-318`
- **Mechanism:** Caller-supplied environment variables are filtered against `BLACK_LISTED_ENV_PATTERNS`.
- **Flaw:** Denylist security is inherently brittle. Any unanticipated variable (e.g. library debugging, profiling, internal flags) is passed through to the execution environment.
- **Remediation:** Switch to a **Safe Environment Allowlist** model. Only explicit, documented, non-hazardous variables are permitted from callers.

### Finding 6: Process Termination PID Reuse Hazard (Severity: LOW-MEDIUM)
- **Location:** `src/tacp/core/execution_service.py:474-482`
- **Mechanism:** `cancel_execution()` and `reconcile_orphans()` call `os.killpg(pgid, ...)` solely from the database `pgid`.
- **Flaw:** If the child process died long ago and the OS recycled the PID/PGID, signals could be delivered to an unrelated process.
- **Remediation:** Track live active processes in an in-memory session registry and verify process start time from `/proc/<pid>/stat` or command identity prior to signal dispatch.

### Finding 7: Approval State Machine Concurrency Invariants (Severity: LOW-MEDIUM)
- **Location:** `src/tacp/control/approval.py`
- **Mechanism:** `approve()`, `deny()`, and `revoke()` perform state transitions with read-then-write or partial conditional SQL.
- **Remediation:** Formalize the 6-state state machine (`PENDING`, `APPROVED`, `DENIED`, `REVOKED`, `EXPIRED`, `CONSUMED`) with strict legal transition tables and atomic conditional SQL updates across all mutation pathways.

---

## 4. Documentation vs. Implementation Discrepancy Matrix

| Documented Claim | Source File | Reality in Code | Finding ID |
| :--- | :--- | :--- | :--- |
| "Network isolated execution" | `docs/architecture/` | `subprocess.Popen` runs with full socket access | Finding 2 |
| "Whitelisted binary execution" | `docs/design/` | Explicit paths bypass trusted root check | Finding 1 |
| "Safe bounded environment" | `docs/specs/` | Open denylist passes unlisted variables | Finding 5 |
| "Role-based authorization" | `docs/architecture/` | Direct checks on `principal.id == "operator"` | Finding 4 |
| "Resource governed I/O" | `docs/specs/` | Floods continue looping until timeout | Finding 3 |

---

## 5. Audit Conclusion

The TACP v0.4.0-rc.1 baseline provides a strong foundation with 618 passing tests, zero arbitrary shell primitives, strict working directory jail enforcement, and cryptographic audit logging. However, the findings detailed above represent security boundaries that are claimed or implied but not robustly enforced.

**Recommendation:** Proceed immediately to Phase 5 hardening. Implement the fixes in order: Executable Identity -> Environment Allowlist -> Network Truth Model -> Resource & Flooding Governance -> Process Containment & PID Reuse -> Approval State Machine -> Identity Authority Refactor.
