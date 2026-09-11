# TACP Phase 0.5: Independent Bootstrap Audit Report

**Audit Date**: 2026-09-11T02:40:00Z  
**Evaluator**: Lead Staff Engineer, DevOps Lead, Security Auditor  
**Audit Doctrine**: Adversarial Falsification & Empirical Proof  
**Overall Status**: **PHASE 0 VERIFIED WITH LIMITATIONS — HUMAN DECISION REQUIRED**  

---

## 1. Executive Summary

This independent audit evaluated the **TACP (Termux AI Control Plane)** engineering factory established in Phase 0. Rather than accepting previous documentation as ground truth, the audit actively attempted to **falsify** claims through controlled sabotage testing, clean-room reproduction in isolated directories, GitHub API permission probing, and file permission analysis.

The engineering factory is fundamentally sound, functional, and auditable, but the audit revealed three genuine limitations and one false claim in the previous report:
1. **False Claim (Branch Protection)**: Server-side GitHub branch protection and rulesets are **not** active. On a personal GitHub Free account, branch protection for private repositories is blocked by GitHub (HTTP 403). Client-side conventions were conflated with branch protection.
2. **Brittle Dependency State (Remediated)**: A pinned `uv.lock` was not generated or committed in Phase 0. Remediated during Phase 0.5 with commit `1b5d684`.
3. **Partial Agent Self-Modification Control**: Antigravity agents operate as user `u0_a316` and therefore possess technical OS write permissions to `.agents/rules/`, `verify`, and CI files. Governance is enforced by behavioral prompt rules and git auditability, but lacks OS-level DAC/MAC immutability.
4. **Shallow Test Assertion Coverage**: The reported "100% test coverage" covers only structural package metadata (`src/tacp/__init__.py`), not domain logic.

---

## 2. Engineering Factory Scorecard

| Dimension | Grade | Assessment |
|---|:---:|---|
| **Repository Governance** | **C** | Clean git structure, Conventional Commits, issue & PR templates; but server-side branch protection is unavailable (HTTP 403) on GitHub Free. |
| **Agent Governance** | **B** | 8 well-scoped role rules and Project Constitution; behavioral compliance is high, but agent has OS-level write access to governance files. |
| **Reproducibility** | **A** | Clean-room clone in isolated directory passed `./doctor` and `./verify` identically; `uv.lock` now committed. |
| **Testing Infrastructure** | **B+** | Deterministic runner, ShellCheck, Ruff format/lint, Mypy strict; pytest setup verified; current tests are baseline only. |
| **Security Controls** | **A-** | Zero-secret scanner verified via sabotage injection; path traversal baseline active; STRIDE threat model cataloged; pip-audit working. |
| **CI / CD Pipelines** | **A** | GitHub Actions matrix (3.11, 3.12, 3.13) and Security pipeline verified passing on GitHub; least-privilege token permissions. |
| **Dependency Management** | **A-** | `uv.lock` locked 42 packages with cryptographic hashes; native Termux packages used for heavy tools (Ruff). |
| **Secret Management** | **A** | Zero secrets detected in tracked files, git history, or shell history; automated regex scanner enforces prohibition. |
| **Evidence Standard** | **B+** | Machine-readable evidence JSON written to `artifacts/verification/`; timestamps, commit SHAs, and exit codes recorded. |
| **Termux Compatibility** | **A-** | Android 16 Bionic paths, shebang fixes, non-root constraints, and `/tmp` limitations correctly handled. |
| **MCP Tooling Readiness** | **B** | Standard specs and versions cataloged; clean development state; MCP Inspector not installed locally yet. |

**Overall GPA**: **3.45 / 4.00 (B+)**

---

## 3. Sabotage Failure-Injection Results

Six controlled failure-injection tests were executed against the canonical local verifier (`./verify`):

| Test ID | Failure Mode Injected | Targeted Stage | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|
| **Sabotage A** | Indentation error in Python source | Stage 2 (`format`) | Fail Stage 2 (Exit 1) | `invalid-syntax: Unexpected indentation` (Exit 1) | **PROVEN** |
| **Sabotage B** | Unused import (`import os`) | Stage 3 (`lint`) | Fail Stage 3 (Exit 1) | `F401 os imported but unused` (Exit 1) | **PROVEN** |
| **Sabotage C** | Mismatched type assignment (`x: int = "str"`) | Stage 4 (`typecheck`) | Fail Stage 4 (Exit 1) | `Incompatible types in assignment` (Exit 1) | **PROVEN** |
| **Sabotage D** | Inverted unit assertion (`assert 1 == 2`) | Stage 5 (`unit_tests`) | Fail Stage 5 (Exit 1) | `AssertionError: assert 1 == 2` (Exit 1) | **PROVEN** |
| **Sabotage E** | Injected active API token pattern into docs | Stage 6 (`security_tests`) | Fail Stage 6 (Exit 1) | `Potential secret pattern found: ghp_...` (Exit 1) | **PROVEN** |
| **Sabotage F** | Vulnerable package specification (`urllib3==1.26.4`) | Stage 7 (`pip_audit`) | Fail Stage 7 (Exit 1) | `Found 18 known vulnerabilities` (Exit 1) | **PROVEN** |

**Conclusion**: `./verify` is genuinely deterministic, catches defects loud and early, never fakes green passes, and halts immediately on the first failing stage.

---

## 4. Clean-Room Reproducibility Audit

A clean-room test was conducted by cloning `The-habib/tacp` fresh into an isolated temporary path (`~/projects/tacp-repro-test`):
1. **Initial Clone**: `./doctor --json` correctly diagnosed the absence of `.venv` and flagged `Issues: 1` with a non-zero exit code.
2. **Environment Bootstrap**: Running `uv venv` and `uv pip install` completed cleanly without compiling native Rust crates.
3. **Subsequent Doctor Run**: `./doctor` passed 15/15 checks cleanly.
4. **Local Verification**: `./verify` executed all 7 stages and completed with `OVERALL_STATUS: PASS` in 35 seconds.
5. **Lockfile Hardening**: `uv.lock` was formally committed (`1b5d684`) to ensure reproducible dependency resolution across all future environments.

---

## 5. Critical Findings & Governance Gaps

### Finding 1: GitHub Server-Side Branch Protection is Unavailable
- **Reality**: On personal GitHub accounts, private repositories require a GitHub Pro upgrade to enable branch protection rulesets and branch restrictions (HTTP 403).
- **Impact**: Any contributor or agent with push tokens can technically push directly to `main` without an approved PR or passing CI.
- **Remediation**:
  - Acknowledge this honestly: do not claim branch protection exists.
  - Implement client-side pre-push hooks that block pushes to `main` unless `./verify` passes.
  - Require PR-based workflows as a constitutional policy for all agent tasks.

### Finding 2: Agent Self-Modification Risk (Filesystem Permissions)
- **Reality**: The Antigravity agent executes with the Linux user identity `u0_a316`. All repository files (including `.agents/rules/`, `verify`, and `.github/workflows/`) are writable by `u0_a316`.
- **Impact**: While Constitutional Rule 20 strictly forbids self-modification, there is no OS-level MAC/DAC barrier preventing a rogue agent from altering its own rules or modifying `./verify` to exit 0.
- **Remediation**:
  - Mark files as read-only (`chmod 444`) where practical.
  - Verification script must check its own git diff / checksum before running.
  - Reviewer Agent role must explicitly audit git diffs for modifications to governance files.

### Finding 3: Test Suite Depth is Minimal
- **Reality**: `test_skeleton.py` achieves 100% line coverage of `src/tacp/__init__.py`, but only tests package string metadata.
- **Impact**: Future features must not rely on simple line coverage as proof of correctness.
- **Remediation**: Require negative, boundary, and adversarial test cases for every new feature in Phase 1+.

---

## 6. Phase 1 Entry Criteria

Before initiating **Phase 1: First Vertical Slice (Workspace Inspection Service)**, the following criteria must be met:

- [x] Environment Discovery complete and verified on Android 16.
- [x] Project Constitution and Agent Rules committed and active.
- [x] Quality toolchain (Ruff, Mypy, Pytest, pip-audit) verified locally and in CI.
- [x] Deterministic local verifier (`./verify`) proven via 6 sabotage tests.
- [x] Clean-room reproducibility verified from clean checkout.
- [x] `uv.lock` committed to git.
- [x] GitHub Actions CI and Security workflows passing on `origin/main`.
- [x] Branch protection limitations documented honestly.
- [ ] **Human Owner Sign-Off**: The CEO/Product Owner explicitly acknowledges the audit findings and authorizes Phase 1 implementation.

---

## 7. Final Declaration

### Status: **PHASE 0 VERIFIED WITH LIMITATIONS — HUMAN DECISION REQUIRED**

The engineering factory is verified, reproducible, and ready. Human Owner review and authorization is required to proceed to Phase 1.
