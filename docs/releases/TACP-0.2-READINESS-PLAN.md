# TACP 0.2 Readiness Plan & Quality Gate Framework

**Document:** `docs/releases/TACP-0.2-READINESS-PLAN.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**Release Engineer:** Antigravity Release & QA Lead  
**Target Release:** TACP 0.2 (`v0.2.0`)  
**Date:** September 11, 2026  

---

## 1. Quality Gates (Gate A through Gate H)

Progression toward the TACP 0.2 release is controlled by 8 sequential quality gates. No gate may be skipped, circumvented, or silently converted to a pass:

```
[GATE A: Architecture & Design Package]       --> CURRENT GATE: All 19 design docs complete
                  │
                  v
[GATE B: Threat Model & Risk Analysis]       --> STRIDE analysis & 88-case security matrix complete
                  │
                  v
[GATE C: Test Matrix & Regression Baseline]   --> Read-only regression (269 tests) frozen & passing
                  │
                  v
[GATE D: First Vertical Slice Verified]       --> workspace.patch (single text file) fully verified
                  │
                  v
[GATE E: Security Red-Team Pass]             --> Adversarial sabotage & injection tests pass
                  │
                  v
[GATE F: Real-Device Android Validation]      --> Executed directly on Android Termux aarch64
                  │
                  v
[GATE G: Clean-Room Install & Bootstrap]      --> Fresh git clone in clean directory passes install
                  │
                  v
[GATE H: Release Candidate Verification]      --> v0.2.0-rc.1 tagged, verified, and signed off
```

---

## 2. Release Status Classifications

TACP strictly uses evidence-based status designations. The phrase *"100% verified"* is prohibited unless accompanied by the specific evidence level:

1. **DESIGN COMPLETE**: All architectural documents authored, cross-checked, and reviewed without blockers.
2. **IMPLEMENTATION COMPLETE**: Source code written in branch; passes formatting and linting.
3. **LOCALLY VERIFIED**: Passes `./doctor` (15/15) and `./verify` (all stages) on developer machine.
4. **CI VERIFIED**: Passes automated GitHub Actions matrix across supported Python versions (3.11, 3.12, 3.13, 3.14).
5. **SECURITY VERIFIED**: All 88 security baseline cases and `pip-audit` vulnerability scans passing.
6. **MCP VERIFIED**: Official `@modelcontextprotocol/inspector` validates all exposed tools under `--strict` mode.
7. **DEVICE VERIFIED**: Validated directly on a physical Android Termux device with real flash storage and process tree.
8. **RELEASE CANDIDATE**: Candidate tagged (e.g. `v0.2.0-rc.1`) with complete release notes and checksums.
9. **RELEASE READY**: Approved by Human Owner with full evidence manifest and committed lockfile.

---

## 3. The 15 Phase 2 Success Criteria (PART LXXXVI)

Phase 2 will be declared successful and release-ready only when all 15 criteria are demonstrated with empirical evidence:

| # | Success Criterion | Verification Proof | Target Slice |
|---|---|---|---|
| **1** | A governed mutation can be requested | MCP tool `tacp_workspace_patch` accepts request | Slice 1 |
| **2** | The request is authorized | PolicyEngine evaluates 5-tier hierarchy; enforces default-deny | Slice 1 |
| **3** | The resource is scoped | Target file resolved within canonical workspace jail | Slice 1 |
| **4** | Risk is assessed | RiskEngine computes R0-R5 risk level & checks L0-L5 autonomy | Slice 1 |
| **5** | Approval is respected | High-risk operations pause for human approval ticket | Slice 1 |
| **6** | The operation is bounded | Output limits, path lengths, and execution timeouts enforced | Slice 1 |
| **7** | The change is auditable | Tamper-evident SHA-256 chained audit entry recorded | Slice 1 |
| **8** | Concurrent conflicts are handled | Base checksum mismatch detects conflict; aborts without overwrite | Slice 1 |
| **9** | Failure is recoverable where promised| Snapshot created prior to mutation; restored on post-verify fail | Slice 3 |
| **10**| Security invariants remain intact | Invariants 1 through 12 verified by automated test harness | Slice 1-5 |
| **11**| Existing read-only capabilities intact | All 269 read-only baseline tests pass without regression | Slice 1-5 |
| **12**| MCP interface exposes only approved tools | Only gated tools exposed; validated by MCP Inspector | Slice 1-5 |
| **13**| Operation works on actual Termux | Physical Android device validation passes | Slice 1-5 |
| **14**| CI independently verifies the change | GitHub Actions workflows pass green | Slice 1-5 |
| **15**| Evidence traceable to commit & spec | Evidence manifest links every test to Part & Git SHA | Slice 1-5 |

---

## 4. Rollback & Downgrade Safety

1. **Database Schema Versioning**: Migrations are strictly numbered and reversible. Downgrading to TACP 0.1 preserves existing workspace and audit records.
2. **Feature Flags Fail Closed**: In any downgraded or corrupted configuration, `mutation.enabled` and `execution.enabled` default to `false`, immediately falling back to safe read-only inspection.
