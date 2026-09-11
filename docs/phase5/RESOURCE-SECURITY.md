# TACP Phase 5: Resource Governance and Output Flooding
**Document ID:** `TACP-RES-GOV-001`  
**Classification:** System Architecture Specification  
**Release Target:** v0.4.0-rc.1 Hardening / Phase 5  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Resource Governance Model

Under Android/Termux `aarch64`, TACP operates in user-space inside the Android application sandbox. Resource controls must distinguish:
- **APPLICATION-LEVEL GOVERNANCE:** Implemented via application monitoring loops, non-blocking I/O multiplexing (`select()`), and process-group signal dispatch (`killpg`).
- **OS-LEVEL ENFORCEMENT:** Enforced by the Android Linux kernel (cgroups, SELinux policies, Android Low-Memory Killer `LMK`).

TACP explicitly does **not** claim kernel cgroup/namespace containerization where none exists.

---

## 2. Resource Controls Matrix

| Dimension | Default Limit | Maximum Hard Cap | Enforcement Level | Breach Outcome |
| :--- | :--- | :--- | :--- | :--- |
| **Wall-Clock Duration** | 15 seconds | 60 seconds | Application (`select()` deadline) | Immediate SIGTERM, 1.5s grace, SIGKILL escalation. Status `TIMED_OUT`. |
| **Max Argument Count** | 64 arguments | 64 arguments | Application (`validate_argv`) | Pre-execution `TacpValidationError`. Zero process spawned. |
| **Max Argument Length** | 4,096 bytes | 4,096 bytes | Application (`validate_argv`) | Pre-execution `TacpValidationError`. Zero process spawned. |
| **Environment Keys** | 16 variables | 16 variables | Application (`assemble_env`) | Pre-execution `TacpValidationError`. Zero process spawned. |
| **Environment Value** | 2,048 bytes | 2,048 bytes | Application (`assemble_env`) | Pre-execution `TacpValidationError`. Zero process spawned. |
| **Standard Output (stdout)**| 65,536 bytes | Configurable | Application (Model B Stream Cap) | Immediate SIGTERM/SIGKILL to process group. Status `OUTPUT_LIMIT_EXCEEDED`. |
| **Standard Error (stderr)**| 65,536 bytes | Configurable | Application (Model B Stream Cap) | Immediate SIGTERM/SIGKILL to process group. Status `OUTPUT_LIMIT_EXCEEDED`. |
| **Standard Input (stdin)** | 0 bytes (`DEVNULL`)| 0 bytes | OS File Descriptor (`/dev/null`) | Immediate EOF returned to child process. |
| **File Descriptors** | Stdin/out/err only | 3 FDs | OS (`close_fds=True`) | Host sockets and database FDs are not leaked to child. |

---

## 3. Output Flooding Defense: Adoption of Model B

In previous iterations, when a child process produced output exceeding stream limits:
- The byte buffer stopped expanding (`stdout_truncated = True`).
- However, the `select()` loop continued reading and discarding 4096-byte chunks in a tight loop until `timeout_seconds` elapsed.
- A hostile child process executing an infinite loop (e.g. `yes` or unbounded binary output) consumed 100% CPU on mobile processor cores for the full duration of the timeout.

### Model B Implementation
Phase 5 replaces truncate-and-spin with **Model B: Immediate Process Termination**:
1. When incoming chunks on `stdout` or `stderr` breach `max_stdout` or `max_stderr`, the buffer captures the exact remaining bytes up to the limit.
2. `output_limit_exceeded` and truncation flags are set to `True`.
3. The executor immediately calls `_kill_process_group(pgid, process)`, dispatching SIGTERM followed by SIGKILL.
4. Active pipes are closed immediately, breaking the pipe and causing SIGPIPE if any descendants survive.
5. The execution status is recorded as `OUTPUT_LIMIT_EXCEEDED`.

This guarantees that a child process cannot exhaust TACP memory or hold CPU cores hostage through output flooding.
