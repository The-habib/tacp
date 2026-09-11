# TACP Phase 5: Negative API and Primitive Audit Report
**Document ID:** `TACP-NEG-API-001`  
**Classification:** Security Architecture Compliance Report  
**Release Target:** v0.4.0-rc.1 Hardening / Phase 5  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Executive Summary

A comprehensive automated static code analysis was conducted across all Python source modules in `src/` to verify that no hidden, rogue, or un-governed execution pathways exist in the codebase.

The audit searched for 24 high-risk execution primitives, shell invocations, and dynamic code evaluation functions.

---

## 2. Definitive Negative API Finding Matrix

| Primitive / Pattern | Discovered Occurrences | Authoritative Location | Compliance Status | Rationale & Security Governance |
| :--- | :---: | :--- | :---: | :--- |
| `os.system` | **0** | None | **CLEAN** | Strictly forbidden across the entire codebase. |
| `shell=True` | **0** | None | **CLEAN** | Arbitrary shell execution is completely prohibited. |
| `eval()` | **0** | None | **CLEAN** | No dynamic string-to-code execution. |
| `exec()` | **0** | None | **CLEAN** | No dynamic Python execution. |
| `os.popen` | **0** | None | **CLEAN** | Shell pipe creation forbidden. |
| `pty` / `pty.spawn` | **0** | None | **CLEAN** | No pseudoterminal allocation or escape vectors. |
| `os.exec*` | **0** | None | **CLEAN** | Zero process image replacement primitives. |
| `os.fork` | **0** | None | **CLEAN** | Zero unmanaged process forks. |
| `os.kill` | **0** | None | **CLEAN** | Raw PID signaling prohibited (uses process groups). |
| `subprocess.call` | **0** | None | **CLEAN** | Unmanaged helpers prohibited. |
| `subprocess.check_call`| **0** | None | **CLEAN** | Unmanaged helpers prohibited. |
| `subprocess.run` | **0** | None | **CLEAN** | Unmanaged helpers prohibited. |
| `subprocess.Popen` | **1 call site** | `src/tacp/providers/process_executor.py:87` | **GOVERNED** | **Sole authoritative process spawn site.** Invoked strictly with `shell=False`, `start_new_session=True`, and `close_fds=True`. |
| `os.killpg` | **4 call sites** | `process_executor.py:306, 319`, `execution_service.py:485, 487` | **GOVERNED** | Dedicated process group termination with PID reuse defense and audit logging. |

---

## 3. Single Execution Pathway Architecture

Every command execution in TACP follows the single authoritative pipeline:
```
Client (MCP / CLI)
  ↓
RequestContext & Principal Verification
  ↓
PolicyEngine.evaluate_request()
  ↓
ExecutionResolver.resolve_executable_identity() [Trusted Root Invariant]
  ↓
ExecutionResolver.assemble_environment() [Safe Allowlist Model]
  ↓
ExecutionContract [Canonical SHA-256 Hashing]
  ↓
ApprovalEngine (if required) [Single-Use Atomic Conditional SQL]
  ↓
Pre-Execution Database Persistence [STARTING / RUNNING in SQLite WAL]
  ↓
ProcessExecutor.execute() [subprocess.Popen(shell=False, start_new_session=True)]
  ↓
Model B Stream Governance (Non-blocking select with immediate flood termination)
  ↓
Process Reaping & Result Sanitization
  ↓
Post-Execution Persistence & Tamper-Evident Audit Hash Chain Append
```

**Conclusion:** Zero rogue execution paths exist in TACP. All operating system process execution is strictly unified under `ProcessExecutor`.
