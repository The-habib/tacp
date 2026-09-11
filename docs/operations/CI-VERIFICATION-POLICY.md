# TACP CI & Verification Policy
## Architectural Governance, Gate Equality, and Supply Chain Integrity

- **Status:** APPROVED & ENFORCED
- **Version:** 1.0.0
- **Scope:** Local (`./verify`), GitHub Actions (`ci.yml`, `security.yml`), and Device Auditing

---

## 1. Principles of Verification Equality

1. **Gate Equality Principle:**
   Local canonical verification (`./verify`) and automated GitHub CI must execute the identical set of quality, type, security, and integration gates. CI must never run an arbitrary subset of tests while claiming project verification.
2. **Lockfile Enforcement Principle:**
   All builds and test suites in CI must install strictly from the committed `uv.lock` using `uv sync --locked`. Dynamic package resolution during CI is strictly prohibited.
3. **Immutable Action Pinning:**
   All third-party GitHub Actions must be pinned to full 40-character immutable commit SHAs, audited for supply-chain provenance.
4. **Honest Device Boundary:**
   Tests requiring physical Termux / Android device primitives are explicitly tagged `@pytest.mark.device` (DEVICE-ONLY). GitHub CI must not simulate or falsify device execution.
5. **Quality over Test Volume:**
   Test counts must never serve as a proxy for engineering completeness. Every security invariant, failure mode, and concurrency boundary must possess dedicated, falsifiable tests.

---

## 2. Verification Execution Matrix

| Verification Gate | Local `./verify` | PR / Push CI (`ci.yml`) | Security CI (`security.yml`) | Nightly / On-Device |
| :--- | :---: | :---: | :---: | :---: |
| **ShellCheck** | YES | YES | YES | YES |
| **Lockfile Sync (`uv.lock`)** | YES (`uv lock --check`) | YES (`uv sync --locked`) | YES (`uv sync --locked`) | YES |
| **Code Formatting (Ruff)** | YES | YES | - | YES |
| **Code Linting (Ruff)** | YES | YES | - | YES |
| **Type Checking (Mypy)** | YES | YES | - | YES |
| **Version Consistency** | YES | YES | - | YES |
| **Unit Tests (`tests/unit`)** | YES | YES | - | YES |
| **Integration Tests (`tests/integration`)**| YES | YES | - | YES |
| **Security Attack Suite (`tests/security`)**| YES | YES | YES | YES |
| **Failure Injection (`F0-F15`)** | YES | YES | - | YES |
| **Dependency Audit (`pip-audit`)** | YES | - | YES | YES |
| **Package Build Validation** | YES | YES | - | YES |
| **On-Device Hardware Tests** | YES (on device) | SKIPPED (`-m "not device"`) | - | MANDATORY |
| **Official MCP Inspector** | YES (interactive) | - | - | MANDATORY for Release |

---

## 3. GitHub Actions Supply Chain Pinning Record

| Action | Version Tag | Immutable Commit SHA | Upstream Repository | Purpose & Trust Decision |
| :--- | :--- | :--- | :--- | :--- |
| `actions/checkout` | `v4.2.2` | `11bd71901bbe5b1630ceea73d27597364c9af683` | `actions/checkout` | Official GitHub core action for checking out source tree. Pinned to audited release tag. |
| `actions/setup-python` | `v5.4.0` | `42375524e23c412d93fb67b49958b491fce71c38` | `actions/setup-python` | Official GitHub action for provisioning Python runtime environments. |
| `astral-sh/setup-uv` | `v5.3.0` | `1edb52594c857e2b5b13128931090f0640537287` | `astral-sh/setup-uv` | Official Astral action for installing and caching the `uv` toolchain. |

---

## 4. Repository Governance & Control Gaps

- **Current Repository Plan:** GitHub Free (Private)
- **Status Checks:** GitHub CI runs on push and pull requests, generating pass/fail check runs.
- **Identified Control Gap:**
  Server-side branch protection rules and GitHub Rulesets requiring status checks to pass before merging are unavailable on private repositories under the GitHub Free plan.
- **Compensating Controls:**
  Local verification (`./verify`) is enforced as a mandatory pre-commit and pre-push hook. Direct pushes to `main` must only be performed after local verification succeeds.
- **Roadmap:**
  Evaluate upgrading to GitHub Pro or transitioning to public open-source visibility prior to implementing command execution or network control capabilities.
