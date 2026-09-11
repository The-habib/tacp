# TACP Phase 5: Environment Security Model
**Document ID:** `TACP-ENV-MOD-001`  
**Classification:** Security Architecture Specification  
**Release Target:** v0.4.0-rc.1 Hardening / Phase 5  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Paradigm Shift: Allowlist vs. Denylist

Historically, TACP used an unsafe denylist pattern (`BLACK_LISTED_ENV_PATTERNS`). While this blocked known sensitive variables like `AWS_SECRET_ACCESS_KEY` and `LD_PRELOAD`, open denylists suffer from structural weaknesses:
- Unanticipated environment variables from dynamic libraries or runtimes pass through silently.
- Future third-party libraries may introduce new debugging flags (e.g. `MALLOC_CHECK_`, `GCONV_PATH`) that can alter execution behavior or induce memory corruption.

Phase 5 transitions TACP to a **Safe Environment Allowlist** architecture.

---

## 2. Environment Taxonomy

The execution environment is partitioned into four mutually exclusive classes:

### 2.1 Class 1: System-Controlled Variables (Authoritative & Immutable)
These variables are computed and set exclusively by TACP. Any attempt by a caller to specify or override them is silently ignored or overridden:
- `PATH`: Curated minimal string of existing trusted roots (`/data/data/com.termux/files/usr/bin:/system/bin:/usr/bin:/bin`). Never inherits host ambient `PATH`.
- `HOME`: Set to the canonical workspace root directory (`workspace.root.resolve()`).
- `PWD`: Set to the validated working directory within the workspace jail.
- `TMPDIR`: Set to the system temporary directory.
- `LANG`: Set to `C.UTF-8`.
- `LC_ALL`: Set to `C.UTF-8`.
- `TERM`: Set to `dumb` to disable terminal escape codes and full-screen curses applications.

### 2.2 Class 2: Caller-Controlled Variables (Strict Safe Allowlist)
Only variables matching known safe names or safe operational prefixes are accepted from the caller:
- **Explicit Safe Keys:** `TZ`, `COLORTERM`, `FORCE_COLOR`, `NO_COLOR`, `COLUMNS`, `LINES`, `CI`, `DEBUG`, `OUTPUT_FORMAT`, `LOG_LEVEL`, `VERBOSITY`.
- **Safe Operational Prefixes:** `CUSTOM_*`, `APP_*`, `USER_*`, `TEST_*`, `VAR*`.

### 2.3 Class 3: Forbidden Variables (Unconditional Strip & Reject)
Variables matching any of the following patterns are stripped or rejected:
- **Secrets & Credentials:** Any key matching `.*(TOKEN|SECRET|KEY|PASSWORD|AUTH|CREDENTIAL|PRIV|CERT).*`.
- **Cloud & Vendor Tokens:** `TACP_*`, `AWS_*`, `AZURE_*`, `GCP_*`, `GOOGLE_*`, `OPENAI_*`, `ANTHROPIC_*`, `GEMINI_*`, `GITHUB_*`, `GITLAB_*`, `NPM_*`, `PYPI_*`.
- **Dynamic Linker & Loader:** `LD_*`, `DYLD_*`.
- **Interpreter Flags:** `PYTHON*`, `NODE*`, `RUBY*`, `PERL*`, `JAVA*`, `CLASSPATH`, `PHP*`, `LUA*`.
- **VCS & SCM Injections:** `GIT_*`.
- **Shell Internals:** `BASH_*`, `ENV`, `IFS`, `SHELLOPTS`, `PROMPT_COMMAND`.
- **Pagers & Editors:** `PAGER`, `EDITOR`, `VISUAL`, `SUDO_*`, `SYSTEMD_*`.
- **Network & Proxy Settings:** `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`.

### 2.4 Class 4: Future Extension Variables
Variables reserved for future capabilities (such as authenticated secret-broker bridges or scoped API tokens) require explicit future policy capabilities and cannot be injected via `execution.request`.

---

## 3. Limits & Bounds

- **Maximum Variables:** 16 caller-supplied environment variables.
- **Key Constraints:** `^[A-Za-z_][A-Za-z0-9_]{0,63}$`, zero null bytes.
- **Value Constraints:** Maximum 2048 bytes per value, zero null bytes.
- **Sorting & Canonicalization:** Environment pairs are sorted lexicographically by key to ensure reproducible SHA-256 contract hashing.
