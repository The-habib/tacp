# TACP Environment Model Specification
## Base Safe Environment, Secret Isolation & Variable Stripping

- **Standard:** TACP-SPEC-004-ENV
- **Status:** APPROVED SPECIFICATION (GATE A)
- **Phase:** Phase 4 — Controlled Command Execution

---

## 1. The Environment Variable Escalation Threat

Operating system environment variables represent an insidious attack surface. When a process spawns a child without explicitly clearing the environment (`os.environ.copy()`), the child inherits:
1. **Plaintext Secrets:** API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`), database credentials, and session tokens.
2. **Dynamic Linker Overrides:** `LD_PRELOAD` or `LD_LIBRARY_PATH` can force standard POSIX binaries to inject and execute arbitrary shared objects (`.so`) before `main()` is reached.
3. **Interpreter Injection:** `PYTHONPATH`, `NODE_PATH`, or `RUBYLIB` allow arbitrary Python or Node code execution by shadowing standard library imports.
4. **Git Remote Command Execution:** `GIT_SSH_COMMAND` or `GIT_ASKPASS` can turn innocent `git` commands into arbitrary script runners.

TACP enforces a **hermetic environment model**: child processes receive **only** explicitly constructed, sanitized variables.

---

## 2. Base Safe Environment Specification

Every execution begins with an invariant, hardcoded **Base Safe Environment**:

| Variable | Value | Rationale |
| :--- | :--- | :--- |
| `PATH` | `/data/data/com.termux/files/usr/bin:/system/bin` (on Termux) or `/usr/bin:/bin` (on POSIX) | Strictly curated system directories. Prevents local directory execution hijacking. |
| `HOME` | Canonical workspace root | Prevents child from writing config files to parent user home directory. |
| `TMPDIR` | Canonical workspace `.tacp/tmp` or system `/tmp` | Isolates temporary file writes. |
| `PWD` | Canonical resolved working directory | Guarantees consistency with POSIX working directory. |
| `LANG` | `C.UTF-8` | Ensures consistent, UTF-8 deterministic byte output across all platforms. |
| `LC_ALL`| `C.UTF-8` | Prevents locale-dependent formatting anomalies. |
| `TERM` | `dumb` | Instructs child utilities not to emit ANSI color/cursor terminal codes. |

---

## 3. Mandatory Stripping List (Blacklisted Variables)

The following variables are **unconditionally stripped** and may never be inherited or passed from the parent process:

### 1. Secrets & Credentials
- `TACP_*` (all TACP control plane tokens, keys, and internal state)
- `*TOKEN*`, `*SECRET*`, `*KEY*`, `*PASSWORD*`, `*AUTH*`, `*CREDENTIAL*`
- `AWS_*`, `AZURE_*`, `GCP_*`, `GOOGLE_*`
- `OPENAI_*`, `ANTHROPIC_*`, `GEMINI_*`, `MISTRAL_*`
- `GITHUB_*`, `GITLAB_*`, `NPM_*`, `PYPI_*`

### 2. Dynamic Linker & Binary Interceptors
- `LD_PRELOAD`
- `LD_LIBRARY_PATH`
- `DYLD_LIBRARY_PATH`, `DYLD_INSERT_LIBRARIES`

### 3. Language & Runtime Path Poisoning
- `PYTHONPATH`, `PYTHONHOME`, `PYTHONSTARTUP`
- `NODE_PATH`, `NODE_OPTIONS`
- `RUBYLIB`, `RUBYOPT`
- `PERL5LIB`, `PERL5OPT`
- `CLASSPATH`, `JAVA_TOOL_OPTIONS`

### 4. Git & Tool Hook Hijackers
- `GIT_SSH`, `GIT_SSH_COMMAND`, `GIT_ASKPASS`
- `GIT_CONFIG`, `GIT_CONFIG_GLOBAL`, `GIT_CONFIG_SYSTEM`
- `GIT_EXEC_PATH`
- `PAGER`, `EDITOR`, `VISUAL`

### 5. Shell Execution Variables
- `BASH_ENV`, `ENV`, `IFS`, `SHELLOPTS`, `PROMPT_COMMAND`

---

## 4. Caller-Supplied Environment Policy

If an execution request includes optional environment variables (`environment: Dict[str, str]`), the variables must satisfy:
1. **Key Pattern:** Must match regex `^[A-Za-z_][A-Za-z0-9_]{0,63}$`.
2. **Key Blacklist:** Must not match any entry in the Mandatory Stripping List.
3. **Value Limits:** Maximum length of 2048 bytes per value.
4. **Total Size:** Maximum of 16 environment variables, total combined size not exceeding 8192 bytes.
5. **No Null Bytes:** Values containing `\x00` are rejected immediately.

Any request violating these constraints fails validation with `TacpValidationError(ErrorCode.VALIDATION_FAILED)`.
