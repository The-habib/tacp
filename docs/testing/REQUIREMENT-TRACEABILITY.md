# TACP 0.1 Requirement Traceability Matrix

- **Document Version**: 1.0.0
- **Target Release**: TACP 0.1 (`v0.1.0-rc.1`)
- **Traceability Date**: 2026-09-11
- **Status**: **100% TRACEABILITY ACHIEVED**

---

## 1. Traceability Architecture

Every requirement from the TACP PRD (`docs/01-PRD.md`) and Project Constitution (`docs/00-PROJECT-CONSTITUTION.md`) is traced to its implementation module, test suite, and automated gatekeeper check.

```
Constitutional & PRD Requirements
              │
              ▼
   Implementation Modules (src/tacp/)
              │
              ▼
    Automated Test Suites (tests/)
              │
              ▼
  Canonical Gatekeeper Verification (./verify)
```

---

## 2. Requirement Traceability Matrix

| Req ID | Requirement Description | Implementation Module | Automated Test File | Gatekeeper Stage | Verification Status |
|---|---|---|---|---|:---:|
| **REQ-01** | Strict Read-Only Policy Enforcement | `src/tacp/control/policy.py` | `tests/unit/test_policy_engine.py`, `tests/security/test_security_baseline_78.py` | Stage 5 & 6 | **VERIFIED** |
| **REQ-02** | Zero Mutation Primitives in Code | `src/tacp/` (all modules) | `tests/security/test_security_baseline_78.py`, `docs/security/NEGATIVE-API-SURFACE-AUDIT.md` | Stage 3, 5, 6 | **VERIFIED** |
| **REQ-03** | Canonical Path Jail & Symlink Boundary | `src/tacp/providers/filesystem.py` | `tests/unit/test_path_jail.py`, `tests/security/test_security_baseline_78.py` | Stage 5 & 6 | **VERIFIED** |
| **REQ-04** | Secret File Classification (`.env`, `id_rsa`) | `src/tacp/providers/filesystem.py` | `tests/security/test_secret_patterns.py`, `tests/security/test_security_baseline_78.py` | Stage 6 | **VERIFIED** |
| **REQ-05** | In-line Sensitive Token Redaction | `src/tacp/infrastructure/logging.py` | `tests/unit/test_secret_redaction.py`, `tests/security/test_security_baseline_78.py` | Stage 5 & 6 | **VERIFIED** |
| **REQ-06** | UID Process Isolation (`os.getuid()`) | `src/tacp/providers/process.py` | `tests/unit/test_process_service.py`, `tests/security/test_security_baseline_78.py` | Stage 5 & 6 | **VERIFIED** |
| **REQ-07** | Tamper-Evident Audit Logging | `src/tacp/core/audit_service.py` | `tests/unit/test_audit_service.py`, `tests/integration/test_recovery.py` | Stage 5 | **VERIFIED** |
| **REQ-08** | Modern MCP 2026-07-28 Conformance | `src/tacp/access/mcp/server.py` | `tests/integration/test_mcp_contract.py`, `docs/mcp/inspector-session.md` | Stage 5 | **VERIFIED** |
| **REQ-09** | Legacy MCP 2024-11-05 Handshake | `src/tacp/access/mcp/server.py` | `tests/integration/test_mcp_contract.py` | Stage 5 | **VERIFIED** |
| **REQ-10** | Strict Tool Input Schema Conformance | `src/tacp/access/mcp/tools.py` | `tests/integration/test_mcp_contract.py`, MCP Inspector `--strict` | Stage 5 | **VERIFIED** |
| **REQ-11** | Output Size Truncation Caps (64KB, 200, 100) | `src/tacp/infrastructure/config.py` | `tests/unit/test_output_limits.py`, `tests/security/test_security_baseline_78.py` | Stage 5 & 6 | **VERIFIED** |
| **REQ-12** | Command Line Interface Diagnostics | `src/tacp/cli/main.py` | `tests/integration/test_cli.py`, `tests/integration/test_installer.py` | Stage 5 | **VERIFIED** |
| **REQ-13** | Deterministic Bootstrap Installer | `install.sh` | `tests/integration/test_installer.py` | Stage 1 & 5 | **VERIFIED** |
| **REQ-14** | State Continuity & Recovery After Crash | `src/tacp/core/audit_service.py` | `tests/integration/test_recovery.py` | Stage 5 | **VERIFIED** |
| **REQ-15** | Termux Environment Support (Python 3.11+) | `src/tacp/providers/system.py` | `tests/device/test_termux_device.py`, `./doctor` | Stage 5 & `./doctor` | **VERIFIED** |
| **REQ-16** | Strict Type Safety (Zero `Any` leaks) | `src/tacp/` | `mypy --strict` | Stage 4 | **VERIFIED** |
| **REQ-17** | Code Hygiene & Linting | `src/tacp/` | `ruff check`, `ruff format --check` | Stage 2 & 3 | **VERIFIED** |
| **REQ-18** | Dependency Security Scanning | `pyproject.toml` | `pip-audit` | Stage 7 | **VERIFIED** |
| **REQ-19** | OpenAI Adapter Compatibility | `src/tacp/access/mcp/` | `tests/integration/test_openai_tunnel.py` | Stage 5 | **VERIFIED** |
| **REQ-20** | Full 78-Case Security Baseline | `src/tacp/` | `tests/security/test_security_baseline_78.py` | Stage 6 | **VERIFIED** |

---

## 3. Verification Governance

Traceability is continually enforced via the 7-stage canonical verifier (`./verify`):
1. ShellCheck (`install.sh`, `doctor`, `verify`)
2. Ruff formatting
3. Ruff linting
4. Mypy strict type checking
5. Pytest unit, integration, device, and recovery test suites
6. Pytest comprehensive 78-case security suite
7. Pip-audit vulnerability analysis

No pull request or commit may merge without passing all 7 stages.
