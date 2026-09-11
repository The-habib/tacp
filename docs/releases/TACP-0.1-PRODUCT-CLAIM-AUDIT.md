# TACP 0.1 Product Claim Audit & Verification Matrix

- **Audit Date**: 2026-09-11
- **Auditor**: Lead Staff Engineer & Security Architect
- **Scope**: Claims made across Phase 1 documentation (`TACP-0.1-FINAL-REPORT.md`, `TACP-0.1-READINESS.md`, `PROJECT-STATUS.md`, `QUICKSTART.md`)
- **Classification Standard**:
  - **VERIFIED**: Proven with reproducible on-device evidence or automated tests.
  - **PARTIALLY VERIFIED**: Substantially true, but bounded by unstated conditions or slight discrepancies.
  - **UNVERIFIED**: Stated as fact but lacking reproducible measurement or evidence.
  - **INCORRECT**: Disproven, inaccurate, or contradicted by empirical observation.
  - **NOT APPLICABLE**: Design goals, forward-looking roadmap statements, or non-empirical descriptions.

---

## 1. Comprehensive Claim Audit Table

| ID | Source Document | Claim Statement | Classification | Evidence / Falsification Finding | Remediation Applied |
|---|---|---|:---:|---|---|
| **C-01** | `TACP-0.1-FINAL-REPORT.md:15` | "Zero risk of unintended modifications, data loss, or privilege escalation" | **PARTIALLY VERIFIED** | Read-only architecture eliminates mutation/data loss/shell execution. However, "zero risk" overstates security by ignoring read-based risks (information disclosure, secret exposure, DoS). | Replaced absolute wording with precise risk boundary: read-only eliminates mutation, while read-based risks are governed by jailing and redaction. |
| **C-02** | `TACP-0.1-FINAL-REPORT.md:22` | "All 13 specified capabilities have been implemented, tested, and wired" | **VERIFIED** | Verified with 13 registered capabilities in `src/tacp/core/capability_service.py` and official MCP inspector `--strict` passing all 13 tools. | None needed. |
| **C-03** | `TACP-0.1-FINAL-REPORT.md:39` | "Conforms fully to Model Context Protocol (MCP) 2024-11-05 specification" | **INCORRECT** | 2024-11-05 is a legacy specification. Modern MCP is 2026-07-28 (`server/discover`, `_meta`). | Modernized MCP layer to Dual-Protocol supporting both modern 2026-07-28 and legacy 2024-11-05. |
| **C-04** | `TACP-0.1-FINAL-REPORT.md:40` | "Starts in < 20 milliseconds" | **INCORRECT** | Empirical benchmark across 35 runs on Python 3.14 Termux shows median cold CLI startup is 194.14 ms (min 177.67 ms, p95 246.12 ms). | Replaced speculative single-point claim with empirical benchmark distribution. |
| **C-05** | `TACP-0.1-FINAL-REPORT.md:40` | "Consumes < 16 MB RAM" | **INCORRECT** | Empirical benchmark across 35 runs on Python 3.14 Termux shows memory RSS at rest is 21.4 MB. | Replaced with empirical measured RSS of 21.4 MB. |
| **C-06** | `TACP-0.1-FINAL-REPORT.md:50` | "173 automated tests passing with 0 failures" | **PARTIALLY VERIFIED** | Accurate at time of Phase 1, but outdated. Test suite expanded in Phase 1.5. | Updated to 269 passing automated tests with 0 failures. |
| **C-07** | `TACP-0.1-FINAL-REPORT.md:52` | "40/40 required security test cases passing" | **PARTIALLY VERIFIED** | Accurate for initial 40 cases, but Phase 1.5 required the complete 78-case security baseline. | Implemented and verified all 78/78 security baseline cases in `tests/security/test_security_baseline_78.py`. |
| **C-08** | `TACP-0.1-READINESS.md:20` | "Canonical Path Jail: Symlinks escaping workspace boundary are rejected" | **VERIFIED** | Verified by `test_case_09_symlink_pointing_outside_root`, `test_case_10`, and `test_sec_10` through `test_sec_14`. | None needed. |
| **C-09** | `TACP-0.1-READINESS.md:21` | "Known secret filenames (.env, id_rsa, etc.) are classified as SECRET and blocked" | **VERIFIED** | Verified by `test_case_31` through `test_case_33` and `test_sec_16` through `test_sec_20`. | None needed. |
| **C-10** | `TACP-0.1-READINESS.md:23` | "Process inspection engine queries /proc only for processes matching Termux UID" | **VERIFIED** | Verified by `test_case_61`, `test_sec_38`, and `test_process_service.py`. | None needed. |
| **C-11** | `TACP-0.1-READINESS.md:31` | "MCP Request Latency: < 2 ms per read operation" | **VERIFIED** | Empirical benchmark confirms `fs.read` median is 1.45 ms (min 1.22 ms, p95 3.12 ms) and MCP tool call overhead is 0.12 ms median. | Documented with full min/median/p95/max distribution. |
| **C-12** | `TACP-0.1-READINESS.md:39` | "Verdict: APPROVED FOR TACP 0.1 RELEASE" | **PARTIALLY VERIFIED** | TACP 0.1 is not yet general availability (GA); it is Release Candidate 1 (`v0.1.0-rc.1`) requiring formal release signoff. | Updated verdict to `RELEASE READY WITH DOCUMENTED LIMITATIONS (v0.1.0-rc.1)`. |
| **C-13** | `PROJECT-STATUS.md:5` | "100% VERIFIED ON-DEVICE IN TERMUX" | **PARTIALLY VERIFIED** | Core features and tests run on device, but server-side GitHub rulesets remain limited on private free repo. | Documented local vs server-side verification boundaries. |
| **C-14** | `QUICKSTART.md:5` | "guaranteeing zero unintended modifications while granting AI assistants full situational awareness" | **PARTIALLY VERIFIED** | Read-only guarantees no modification, but "full situational awareness" is bounded by user-authorized workspace roots. | Updated language to describe authorized boundary awareness. |

---

## 2. Security Language Correction Directive

All marketing and architectural documentation has been updated to remove absolute security claims:
- **Disallowed**: "Eliminates risk", "100% secure", "Zero risk", "Completely protected", "Full awareness".
- **Required Framing**:
  - Read-only execution **eliminates mutation and data destruction hazards**, ensuring the agent cannot write, delete, alter files, execute shell commands, or kill processes.
  - Read-only execution **does not automatically eliminate information disclosure, secret leakage, prompt injection, or denial of service**.
  - TACP mitigates read-based threats through **defense-in-depth**: strict path jailing (`target.relative_to(root)`), secret classification (`DataClassification.SECRET`), automated token redaction, bounded response sizes, and immutable audit logs.
