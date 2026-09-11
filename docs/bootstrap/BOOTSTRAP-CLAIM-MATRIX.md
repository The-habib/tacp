# TACP Bootstrap Claim Falsification Matrix

**Phase**: 0.5 — Independent Bootstrap Audit  
**Timestamp**: 2026-09-11T02:40:00Z  
**Audit Doctrine**: Falsification & Adversarial Verification  

---

## 1. Claim-by-Claim Evaluation Matrix

| Claim ID | Claim from Previous Bootstrap Report | Actual Evidence Inspected | Verification Method | Result | Limitations & Findings |
|---|---|---|---|---|---|
| **CLM-01** | Python 3.14.6, uv 0.12.12, Node 26.4, Git 2.55, gh 2.100 are installed and operational. | Direct `--version` execution and `./doctor` output. | Read-only inspection & doctor check. | **VERIFIED** | All binaries verified in Termux PATH (`$PREFIX/bin`). |
| **CLM-02** | Termux native `ruff 0.16.7` linter & formatter is installed. | `ruff --version` in PATH; utilized by `./verify`. | Command execution. | **VERIFIED** | Precompiled native ARM64 package replaces slow source compilation. |
| **CLM-03** | Python virtual environment has all quality dev tools installed. | `pytest 9.1.1`, `mypy 2.3.1`, `pip-audit 2.10.1`, `pytest-cov 7.1.0`. | `./doctor --json` and `uv pip list`. | **VERIFIED** | Virtual environment at `.venv` validated. |
| **CLM-04** | Project dependencies are strictly locked and reproducible. | `uv.lock` was initially missing; generated and committed in Phase 0.5 (`1b5d684`). | Directory inspection & `uv lock`. | **PARTIALLY VERIFIED** | **Discovery**: `uv.lock` was NOT generated in Phase 0. Remediated and committed during Phase 0.5 audit. |
| **CLM-05** | Canonical verifier (`./verify`) is deterministic and fails on errors. | Sabotage Tests A-F: Injected format, lint, type, unit test, security, and vulnerable package errors. | Fault injection & exit-code assertion. | **VERIFIED** | `./verify` failed loud with exit code 1 on every single injected defect; recorded exact failure stage. |
| **CLM-06** | Unit test suite achieves 100% test coverage. | `pytest tests/unit --cov=src` output: 2 stmts, 0 miss, 100% cov. | Pytest coverage execution. | **PARTIALLY VERIFIED** | 100% coverage exists on `src/tacp/__init__.py`, but the test is a superficial metadata check. It does not test complex logic. |
| **CLM-07** | Automated security scanner protects against secret leakage. | `tests/security/test_secret_patterns.py` caught synthetic leaked token in Sabotage E. | Adversarial pattern injection. | **VERIFIED** | Proved functional on repository text files. |
| **CLM-08** | GitHub Actions CI matrix runs on every push and PR. | GitHub Actions Run `34532501267` completed with `success`. | GitHub API query via `gh run list`. | **VERIFIED** | Tested across Python 3.11, 3.12, and 3.13. |
| **CLM-09** | GitHub Actions Security & Audit workflow runs ShellCheck and pip-audit. | GitHub Actions Run `34532501342` completed with `success`. | GitHub API query via `gh run list`. | **VERIFIED** | Resolved initial variable interpolation bug; runs cleanly. |
| **CLM-10** | Branch protection and rulesets are configured for `main`. | GitHub API returns HTTP 403: "Upgrade to GitHub Pro or make this repository public". | `gh api repos/The-habib/tacp/branches/main/protection`. | **FALSE** | **Falsified**: Server-side branch protection does NOT exist. Calling client-side conventions "branch protection" is inaccurate. |
| **CLM-11** | Agent self-modification is prevented. | Inspected file permissions of `.agents/rules/`, `verify`, and `.github/`. Owned by `u0_a316`. | `test -w` checks on governance files. | **PARTIALLY VERIFIED** | Agent is constrained by behavioral prompt rules and git auditability, but has OS write permissions to its own governance files. |
| **CLM-12** | Clean checkouts can reproduce the development environment from scratch. | Clean-room clone executed in isolated directory `~/projects/tacp-repro-test`. | Full clone, doctor, venv setup, and `./verify` run. | **VERIFIED** | Exact parity achieved; doctor correctly flagged missing venv before setup. |
| **CLM-13** | Zero TACP application runtime or MCP tools were implemented. | Checked `src/tacp/` and `git status`. | Codebase inspection. | **VERIFIED** | Phase discipline strictly maintained. |

---

## 2. Result Summary

- **VERIFIED**: 9 claims (69%)
- **PARTIALLY VERIFIED**: 3 claims (23%) (Lockfile tracking, unit test depth, agent self-modification limits)
- **FALSE**: 1 claim (8%) (Branch protection on private repo without GitHub Pro)
- **UNVERIFIED**: 0 claims (0%)
