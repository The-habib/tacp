# TACP Phase 5: Release Gate & Capability Expansion Evaluation
**Document ID:** `TACP-REL-GATE-001`  
**Classification:** Architectural Release Decision  
**Target Release:** v0.4.0-rc.1 Hardening / Phase 5 Completion  
**Date:** September 2026  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Release Gate Context & Objective

Phase 5 was instituted not to add commands, but to determine whether TACP's execution architecture is sufficiently trustworthy, robust, and hardened to expand its executable capability set.

The core question before this release gate:

> **Is the execution subsystem trustworthy enough to introduce additional operating-system capabilities without risking sovereignty compromise, command injection, secret leakage, or uncontained process execution?**

---

## 2. 20-Point Formal Gate Conformance Matrix

| # | Evaluation Criterion | Requirement | Verification Status | Evidence Document / Test Suite |
|---|---|---|---|---|
| **1** | **No Arbitrary Shell** | Zero `shell=True`, `os.system()`, `bash -c` | **CONFORMANT (100%)** | `NEGATIVE-API-AUDIT.md`, `test_sabotage_07` |
| **2** | **Zero Runtime Dependencies** | Python standard library only | **CONFORMANT (100%)** | `pyproject.toml`, `COMPATIBILITY-MATRIX.md` |
| **3** | **Trusted Root Verification** | Executables must reside in safe roots | **CONFORMANT (100%)** | `EXECUTABLE-IDENTITY.md`, `test_cat02` |
| **4** | **Multicall Binary Policy** | Symlink target verified in allowlist | **CONFORMANT (100%)** | `EXECUTABLE-IDENTITY.md`, `test_cat04` |
| **5** | **Inode & Digest TOCTOU** | SHA-256 binary digest cached & checked | **CONFORMANT (100%)** | `EXECUTABLE-IDENTITY.md`, `test_cat05` |
| **6** | **Safe Environment Model** | Allowlist + forbidden patterns enforced | **CONFORMANT (100%)** | `ENVIRONMENT-MODEL.md`, `test_cat06`, `test_cat07` |
| **7** | **Secret Redaction** | Zero credentials leaked to env/logs | **CONFORMANT (100%)** | `ENVIRONMENT-MODEL.md`, `test_cat07` |
| **8** | **Network Truth Model** | Unenforced state truthfully recorded | **CONFORMANT (100%)** | `SECURITY-BOUNDARY.md`, `test_cat08` |
| **9** | **Model B Stream Limiting** | Immediate process group kill on limit | **CONFORMANT (100%)** | `RESOURCE-SECURITY.md`, `test_cat09`, `test_sabotage_10` |
| **10** | **Process Group Isolation** | `os.setsid()` and `os.killpg()` on termination | **CONFORMANT (100%)** | `PROCESS-CONTAINMENT.md`, `test_cat11` |
| **11** | **PID Reuse Defense** | ActiveProcess tracking + start_time check | **CONFORMANT (100%)** | `PROCESS-CONTAINMENT.md`, `test_cat12`, `test_sabotage_11` |
| **12** | **Atomic Approval FSM** | 6-state machine with atomic conditional SQL | **CONFORMANT (100%)** | `APPROVAL-STATE-MACHINE.md`, `test_cat14`, `test_sabotage_02` |
| **13** | **Zero Name Privilege** | Roles, tiers, and authorities replace names | **CONFORMANT (100%)** | `IDENTITY-AUTHORITY.md`, `src/tacp/control/identity.py` |
| **14** | **Cryptographic Contracts** | Canonical SHA-256 contract hash binding | **CONFORMANT (100%)** | `EXECUTION-CONTRACT.md`, `test_property_contract` |
| **15** | **Crash & Orphan Recovery** | Stuck executions reaped on startup | **CONFORMANT (100%)** | `RECOVERY.md`, `test_cat16` |
| **16** | **Emergency Stop Mechanism** | Immediate termination of all active procs | **CONFORMANT (100%)** | `RECOVERY.md`, `test_cat32`, `tacp emergency-stop` |
| **17** | **MCP Protocol Conformance** | Strict schema parsing & untrusted adapter | **CONFORMANT (100%)** | `MCP-CONFORMANCE.md`, `test_cat18`, `test_cat19` |
| **18** | **Negative API Audit** | Exactly 1 audited `Popen` in codebase | **CONFORMANT (100%)** | `NEGATIVE-API-AUDIT.md` |
| **19** | **Adversarial & Sabotage Suite** | 51 attack tests + 12 sabotage tests pass | **CONFORMANT (100%)** | `SECURITY-TEST-REPORT.md`, `test_sabotage.py` |
| **20** | **Real Android/Termux Validation**| Tested on physical Android 13 `aarch64` | **CONFORMANT (100%)** | `DEVICE-SECURITY-REPORT.md`, `test_termux_execution.py`|

---

## 3. Capability Expansion Gate Decision

### Finding
The execution architecture has satisfied all 20 security criteria without exception. The defense-in-depth model guarantees that process execution is bound to an immutable cryptographic contract, governed by an atomic state machine, isolated in process groups, strictly capped in resource consumption, stripped of environmental hazards, and truthfully audited.

### Decision
**THE GATE IS OPEN FOR CONTROLLED CAPABILITY EXPANSION (PHASE 6).**

TACP's execution core is certified trustworthy to expand beyond the initial baseline (`printf`, `echo`, `true`).

---

## 4. Expansion Policy & Prerequisites for Future Executables

To maintain sovereignty and safety, any executable proposed for inclusion in Phase 6 MUST satisfy the following strict 5-point expansion protocol:

1. **Deterministic Binary Identity:**
   - Must reside within `SAFE_SEARCH_PATHS`.
   - Must resolve to a permitted target or verified multicall backend.
   - Must have a static SHA-256 digest recorded in the capability registry.

2. **Strict Argument Grammar & Schema:**
   - No generic `*args` passthrough.
   - Dedicated validator defining exact allowed flags, positional arguments, and value formats.
   - Disallow arguments capable of arbitrary code execution (e.g. `python -c`, `find -exec`, `awk 'system()'`).

3. **Threat Model & Adversarial Validation:**
   - Dedicated threat analysis document identifying failure modes and escape vectors.
   - Minimum 5 adversarial tests targeting that specific utility before merge.

4. **Approval & Capability Tier Classification:**
   - Classification into read-only, mutating, or elevated trust tiers.
   - Mutating and elevated capabilities require interactive operator approval tickets.

5. **Resource Budget Enforcement:**
   - Explicit timeout, memory limit, and stdout/stderr byte ceiling tailored to the utility.

---

## 5. Release Recommendation

1. **Tag Baseline:** `v0.4.0` Final.
2. **Phase 5 Status:** Complete, Hardened, and Formally Signed Off.
3. **Next Milestone:** Phase 6 — Controlled Capability Expansion (Inspection utilities: `stat`, `file`, `ls`, `grep`).
