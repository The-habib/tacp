# TACP Phase 5: Security Boundary Specification
**Document ID:** `TACP-SEC-BOUND-001`  
**Classification:** TACP System Security Architecture  
**Release Target:** v0.4.0-rc.1 Hardening / Phase 5  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Scope & Objective

This document defines the exact security properties, technical enforcement mechanisms, concrete operational guarantees, and fundamental platform limitations of TACP (Termux AI Control Plane) operating on Android/Termux `aarch64`.

TACP does **not** rely on vague marketing claims. In TACP:
- Application-level path validation is **not** an OS kernel sandbox.
- Process group termination (`killpg`) is **not** a hardware virtual machine boundary.
- Unset proxy variables are **not** kernel network isolation.
Every guarantee is paired with its exact enforcement primitive and physical boundary limitation.

---

## 2. Definitive Security Boundary Matrix

| Property | Guarantee | Technical Enforcement Mechanism | Platform / Physical Limitation | Regression / Verification Test |
| :--- | :--- | :--- | :--- | :--- |
| **Filesystem Mutation** | Mutations confined strictly inside workspace directory tree | Python `pathlib.Path.resolve()`, relative path traversal checks (`is_relative_to`), atomic rename replacement, pre-mutation snapshot | Application-level jail. Does not defend against symlink race attacks (TOCTOU) if another process mutates workspace simultaneously. | `tests/unit/test_patch_service.py`, `tests/security/test_slice1_security.py` |
| **Working Directory** | Process `cwd` is locked inside workspace root | `ExecutionResolver.resolve_working_directory()` verifies `target.is_relative_to(clean_root)` and rejects null bytes / `..` | Process itself could invoke `chdir` via system calls if it was a language runtime (mitigated by strict binary allowlist). | `tests/unit/test_execution_resolver.py::test_cwd_escape_rejected` |
| **Executable Identity** | Only approved system binaries (`printf`, `echo`, `true`) are executable | Canonical absolute path resolution, verification that resolved realpath resides within `SAFE_SEARCH_PATHS`, inode ownership/permissions check | Relies on OS filesystem integrity of `/system/bin` and `/data/data/com.termux/files/usr/bin`. | `tests/security/test_execution_security.py` |
| **Executable Integrity** | Binary cannot be substituted or swapped for malicious interpreter | Trusted root restriction, symlink resolution to realpath, ELF/basename validation, non-world-writable parent checks | Package manager updates to Termux packages change binary digests; system partition is read-only. | `tests/unit/test_execution_resolver.py` |
| **Arbitrary Shell Execution** | Shell commands and shell string parsing are impossible | `subprocess.Popen(shell=False)` with direct `argv: List[str]`. Strict negative API grep gate in CI. | None at TACP layer; `sh -c` cannot be passed because `sh` is forbidden. | `tests/security/test_slice1_security.py`, negative API CI |
| **Process Group Containment** | Child process and descendants run in dedicated process session | `subprocess.Popen(start_new_session=True)`. Session leader PGID == PID. | If child invokes `setsid()` or creates a new process group, grandchildren escape the session PGID. | `tests/unit/test_process_executor.py` |
| **Process Lifetime & Timeout** | Wall-clock execution is bounded to $\le 60$ seconds | Non-blocking `select()` loop with deadline monitoring, SIGTERM escalation to SIGKILL on process group | Granularity of `select()` loop sleep ($\sim 10-50$ms); SIGKILL is uncatchable, but uninterruptible sleep (kernel D-state) cannot be terminated. | `tests/unit/test_process_executor.py::test_timeout_kills_process_group` |
| **Process Signals** | Signals are dispatched cleanly to entire process group | `os.killpg(pgid, signal.SIGTERM)` followed by 1.5s grace period and `SIGKILL` | Unprivileged Termux cannot signal processes owned by other Android apps or root. | `tests/unit/test_process_executor.py` |
| **PID Reuse Defense** | Old execution cancellation never signals recycled OS PIDs | In-memory active process registry binding `execution_id`, `pid`, `pgid`, and spawn timestamp | If TACP process restarts, historical PIDs in SQLite cannot be killed without verifying `/proc/<pid>/stat` start-time ticks. | `tests/security/test_execution_security.py` |
| **Child & Descendant Processes** | Subprocesses spawned by child are terminated upon timeout/exit | `os.killpg(pgid, ...)` kills all processes retaining the session PGID | Fork bombs before PGID setup or double-fork (`fork() -> fork() -> setsid()`) break PGID tracking. | `tests/unit/test_process_executor.py` |
| **Process Privileges** | Execution runs strictly under Termux UID/GID | Inherited from parent TACP process; zero `setuid`, zero root elevation | Cannot drop privileges lower than Termux application sandbox UID without root. | `tests/device/test_termux_execution.py` |
| **Standard Input (stdin)** | Child process cannot read user keystrokes or interactive prompts | `subprocess.Popen(stdin=subprocess.DEVNULL)` | Processes expecting interactive TTY fail or exit immediately. | `tests/unit/test_process_executor.py` |
| **Standard Output (stdout)** | Bounded buffer, terminal escape sanitized, immediate termination on flood | Non-blocking read into bytearray capped at `max_stdout_bytes`. Model B: immediate PGID kill if cap exceeded. ANSI escape stripping. | Sanitization is applied on output string decode; binary non-UTF8 output is lossy replaced (`errors="replace"`). | `tests/unit/test_process_executor.py` |
| **Standard Error (stderr)** | Bounded buffer, sanitized, immediate termination on flood | Identical to stdout (separate stream cap). Model B termination on excess. | Stderr and stdout have independent limits. | `tests/unit/test_process_executor.py` |
| **File Descriptors** | Child process inherits only stdin, stdout, stderr | `subprocess.Popen(close_fds=True)` | Python standard file descriptor leak prevention; `/dev/null` opened for stdin. | `tests/unit/test_process_executor.py` |
| **Environment Isolation** | Child receives curated minimal environment; no host secrets | Safe Allowlist model: `PATH`, `HOME`, `PWD`, `TMPDIR`, `LANG`, `LC_ALL`, `TERM`, plus vetted caller whitelist | Not a chroot/container mount namespace. Child can read files world-readable to Termux UID. | `tests/unit/test_execution_resolver.py` |
| **Network Isolation** | **NETWORK_UNENFORCED**: TACP does NOT provide kernel network isolation | Application policy level: network-capable binaries (`curl`, `wget`, `nc`, `ssh`) are forbidden | **LIMITATION**: On unrooted Android, socket syscalls cannot be blocked without `seccomp` or network namespaces. | `tests/security/test_execution_security.py` |
| **Resource Usage (CPU/Mem)** | Wall-clock timeout and output byte cap | Timeout kills process; output cap kills flooder | CPU throttling and hard memory rlimits (`RLIMIT_AS`) are application-level or limited by Android OS cgroups. | `tests/unit/test_process_executor.py` |
| **Crash Recovery** | TACP process crash leaves deterministic database records | SQLite WAL journaling, pre-execution persistence (`STARTING`/`RUNNING`), startup reconciliation (`reconcile_orphans`) | Processes running when TACP dies become orphans; detected on next startup via `/proc` probe. | `tests/unit/test_execution_service.py` |
| **Emergency Stop** | Global kill switch terminates all active executions | Process group termination of all registered active executions with audit event logging | Restricted to executions owned by current TACP database / session. | `tests/unit/test_execution_service.py` |
| **MCP Caller Identity** | MCP requests mapped to explicit `RequestContext` and `Principal` | MCP adapter extracts client info, policy engine evaluates principal role/tier | MCP JSON-RPC stdio transport does not have mTLS or OS-level peer credentials. | `tests/unit/test_mcp_tools.py` |
| **Approval Identity & Scope** | Approvals are 5-dimensionally bound (principal, action, ws, target, hash) | SHA-256 token hashing, single-use atomic conditional consumption (`UPDATE ... WHERE status='APPROVED'`) | Bearer token secret must be protected from leakage; tokens expire after TTL. | `tests/unit/test_approval.py`, `tests/security/test_security_40.py` |
| **Audit Log Integrity** | Hash-chained tamper-evident event log | SHA-256 `previous_hash` chain, strict append-only SQLite schema, Merkle root verification | Protecting audit log against hostile modification requires external log shipping / read-only filesystem. | `tests/unit/test_audit_service.py` |
| **Android / Termux Context** | Operates inside Android application sandbox UID (`u0_a...`) | SELinux domain `untrusted_app`, no root, no hardware access without Android permissions | Subject to Android OS background execution limits and low-memory killer (LMK). | `tests/device/test_termux_execution.py` |

---

## 3. Explicit Statement of Non-Guarantees

TACP explicitly **DOES NOT** guarantee:
1. **Kernel-level Sandboxing:** There is no Landlock, seccomp-bpf filter, or user namespace wrapping child processes.
2. **Hardware Virtualization:** Execution takes place on the host Android Linux kernel directly.
3. **Network Packet Interception:** If an executable opens a network socket, the operating system kernel permits it unless Android OS permissions or policy allowlists prevent that binary from being invoked.
4. **Immutable Filesystem:** Child processes run with the effective permissions of the Termux user and can write to any file inside `/data/data/com.termux` that is writable by that UID, except as prevented by binary selection and capability policy.
