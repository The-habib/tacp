# TACP Future Command Execution Security Specification & Architecture

**Document ID**: TACP-SPEC-EXEC-01  
**Status**: DESIGN SPECIFICATION ONLY (NO CODE IMPLEMENTED IN PHASE 3)  
**Security Boundary**: Phase 3 Pre-Execution Gate  
**Target Environment**: Android Termux `aarch64` / Linux  

---

## 1. Architectural Philosophy

Future command execution in TACP must be treated as a high-risk capability. Under no circumstances will arbitrary shell strings be passed to `/bin/sh` or `bash`. Execution must follow an explicit, structured, policy-governed POSIX subprocess model with rigid constraints, resource quotas, and full audit traceability.

---

## 2. Answers to the 17 Critical Security Design Questions

### Q1. Command Representation
Commands must be accepted solely as an **argv list of strings** (`List[str]`), where `argv[0]` is the explicit executable name or path, and `argv[1:]` are distinct arguments. Raw multi-command strings containing shell metacharacters (pipes `|`, redirects `>`, semicolons `;`, `&&`, backticks) are rejected by validation before any execution pipeline step.

### Q2. Ban on Shell Invocation
`shell=True` in Python `subprocess` is strictly prohibited. Subprocess creation will use `subprocess.Popen(args=argv, shell=False)`. Bypassing shell interpreters eliminates shell injection, command chaining, and IFS manipulation attacks.

### Q3. Executable Path Resolution & Allowlist
Executable resolution must verify the target binary against an explicit allowlist in configuration:
- Allowed binary directories: Restricted to `$PREFIX/bin` (Termux userland binaries).
- Disallowed binaries: Strict blocklist prohibiting dangerous administrative or network tools without high-tier approval (`su`, `tsu`, `pkg`, `apt`, `sshd`, `netcat`, `nmap`).
- In-workspace scripts: Must be referenced by relative path, reside strictly within workspace jail, and possess executable file bits.

### Q4. Environment Variable Sanitization
Processes must NOT inherit the parent TACP server's ambient environment. A clean, sanitized environment is synthesized:
- Whitelisted keys: `PATH`, `TERM`, `LANG`, `TMPDIR`, `USER`, `HOME`.
- Scrubbed keys: Automatic stripping of `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `SSH_AUTH_SOCK`, `TACP_*` credentials.

### Q5. Working Directory Isolation
The process working directory (`cwd`) must be resolved within an authorized active workspace boundary using TACP's canonical path jail. Attempts to set `cwd` outside the workspace boundary fail policy evaluation.

### Q6. Execution Timeouts
Every execution has a mandatory, non-configurable upper bound (e.g., default 30s, maximum 120s). Enforcement is managed by a background timer or event-loop watcher. If the timeout expires:
1. `SIGTERM` is sent to the process group.
2. A grace period (e.g., 2.0s) is allowed for clean exit.
3. `SIGKILL` is sent if the process group remains alive.

### Q7. Process Group & Orphan Prevention
Subprocesses must be spawned in a dedicated process session using `start_new_session=True` (`os.setsid`). This ensures that on timeout or cancellation, signals are dispatched to `-pid` (the entire process group), preventing orphaned child processes or daemonized escapes.

### Q8. Standard I/O Bounded Buffers & Deadlock Prevention
To prevent pipe deadlock and memory exhaustion:
- `stdout` and `stderr` must be captured via non-blocking pipes or spool files with hard byte limits (e.g., max 512 KB per stream).
- When the buffer exceeds the limit, further output is discarded and marked as truncated.

### Q9. Interactive I/O & Stdin Handling
Interactive TTY sessions are forbidden by default. Standard input (`stdin`) is set to `subprocess.DEVNULL` to prevent commands from hanging indefinitely waiting for human terminal input.

### Q10. Exit Status & Termination Telemetry
The control plane must distinguish and record:
- Normal termination with exit code (`EXIT_SUCCESS` or code `N`).
- Signal termination (e.g., `SIGKILL`, `SIGSEGV`).
- Timeout expiration (`TIMEOUT_EXPIRED`).
- Output truncation flag.

### Q11. Termux Android Signal Handling
Termux operates within an Android application sandbox without root capabilities. Signals like `SIGINT` and `SIGTERM` are handled in userland. Signals must be dispatched via standard POSIX `os.killpg(pgid, signal.SIGTERM)`.

### Q12. Resource Limits & Quotas
Subprocess resource quotas should be applied at pre-exec time via `preexec_fn` or `resource.setrlimit`:
- Maximum CPU time (`RLIMIT_CPU`).
- Maximum virtual memory / address space (`RLIMIT_AS`).
- Maximum open file descriptors (`RLIMIT_NOFILE`).

### Q13. Policy Classification & Approval Tiering
Commands must be categorized into distinct risk tiers:
- **Tier 1 (Benign Read-Only)**: E.g., `git status`, `git log`, `ls`, `cat`, `python --version`. Permitted to restricted agent principals.
- **Tier 2 (Governed Workspace Mutating)**: E.g., `git commit`, `npm test`, `pytest`, `cargo build`. Permitted with dry-run or low-friction human consent.
- **Tier 3 (Destructive / Unbounded)**: E.g., `git clean -fdx`, `rm`, build tools that touch network. Requires explicit human approval ticket with SHA-256 token verification.

### Q14. Concurrency & Mutual Exclusion
Command execution on a workspace must acquire an exclusive workspace execution lock (`{workspace_id}:exec`) via `LockService`. Concurrent mutating commands within the same workspace are rejected with `TacpConflictError`.

### Q15. Cryptographic Audit Logging
All executed commands must be recorded in the tamper-evident audit hash chain:
- Redacted argv list.
- Execution duration (ms).
- Process exit code or termination signal.
- Digest of stdout and stderr.
- Predecessor and entry SHA-256 hashes.

### Q16. Rollback & Compensation Model
Unlike unified text diffs, arbitrary command execution cannot be automatically rolled back. Therefore:
- The control plane will offer pre-command workspace checkpoints (snapshotting modified workspace files or Git commit hashes) prior to command dispatch.
- If execution fails or is cancelled, compensation instructions or checkpoint restoration can be initiated.

### Q17. Android / Termux Environmental Quirks
- **Phantom Process Killer**: Android 12+ kills background child processes consuming high CPU or exceeding 32 processes.
- **Battery Optimization / Doze Mode**: Long-running background processes may be frozen by Android OS unless Termux acquired a partial wake-lock.
- **SELinux Restrictions**: Subprocesses cannot execute binaries outside allowed Termux prefixes or workspace directories marked `noexec`.

---

## 3. Implementation Plan for Phase 4+

This design specification forms the strict blueprint for Phase 4. No execution code is active or present in TACP v0.3.1-rc.1.
