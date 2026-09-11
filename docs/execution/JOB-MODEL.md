# TACP Job System, Process Management & Command Execution

**Document:** `docs/execution/JOB-MODEL.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**Execution Lead:** Antigravity Principal Execution Engineer  
**Date:** September 11, 2026  

---

## 1. Separation of Job from Process

A fundamental design requirement in TACP Phase 2 is the separation of **Job** from **Process**:
- **Job**: A durable, persistent platform abstraction tracking intent, contract, lifecycle states, logs, and audit evidence. Survives client disconnects.
- **Process**: An ephemeral operating-system process (`PID`) spawned inside Android Termux, bounded by OS signals and resource limits.

A single Job owns zero or more Processes across its lifecycle.

```
+========================================================================+
| JOB (Durable Entity in SQLite)                                         |
| - ID: job-uuid-1234                                                    |
| - State: RUNNING                                                       |
| - Contract: ExecutionContract(capability="command.exec", argv=[...])   |
+========================================================================+
                                   │
                                   v owns
+------------------------------------------------------------------------+
| PROCESS SUPERVISOR (OS Layer)                                          |
| - PID: 18274 (PGID: 18274 via setsid)                                  |
| - Executable: /data/data/com.termux/files/usr/bin/python3               |
| - Memory Budget: 256 MB                                                |
| - Timeout: 60s hard kill                                               |
+------------------------------------------------------------------------+
```

---

## 2. Command Execution Specification (`execution.request`)

TACP **does not provide** a raw `execute_any_command(cmd_string)` interface.

All command invocations require structured `argv` arrays with explicit executables:

```python
@dataclass(frozen=True)
class ExecutionRequest:
    request_id: str
    executable: str  # Absolute path or vetted binary name (e.g. "pytest")
    arguments: List[str]  # Array of string arguments (NO shell expansion)
    working_directory: Path  # Must resolve inside authorized workspace
    environment_variables: Dict[str, str]  # Sanitized, explicit key-values only
    timeout_seconds: int  # Wall-clock execution timeout
    max_output_bytes: int  # Output buffer cap (default: 1 MB)
    network_enabled: bool  # Explicit network permission flag
    principal: Principal  # Authenticated caller
```

### Safety Rules for Command Execution
1. **No Implicit Shell**: `shell=False` is mandatory in `subprocess.Popen`. Invocations pass directly to `execve`.
2. **Argument Array Integrity**: Spaces, quotes, and metacharacters (`;`, `&`, `|`, `` ` ``, `$`) are passed as literal arguments to the executable, neutralizing shell injection attacks.
3. **PATH Sanitization**: `PATH` is fixed to trusted Termux directories (`/data/data/com.termux/files/usr/bin:/data/data/com.termux/files/usr/bin/applets`). User or workspace directories are never prepended to `PATH`.
4. **Process Group Termination**: Child processes are spawned in new process groups (`start_new_session=True`). On timeout or cancellation, signals (`SIGTERM`, then `SIGKILL`) are sent to the entire process group (`-pgid`), preventing orphaned background child processes.

---

## 3. Command Classification & Risk Categories

Commands are classified by capability and risk:

| Class | Executables | Risk | Default Policy |
|---|---|---|---|
| **SAFE** | `pwd`, `ls`, `git status`, `git log`, `git diff`, `pytest`, `python -m unittest` | `R0` / `R1` | `ALLOW` in workspace |
| **CONTROLLED**| `python`, `node`, `ruff`, `mypy`, `git commit`, `uv pip install` | `R2` / `R3` | `ALLOW` with active lease / `REQUIRE_APPROVAL` |
| **DANGEROUS** | `rm`, `git reset --hard`, `git clean`, `pkill`, `kill` | `R4` | `REQUIRE_APPROVAL` (Mandatory human prompt) |
| **CRITICAL** | `su`, `sudo`, `chown`, `chmod 777`, `setenforce`, `iptables` | `R5` | `DENY_PERMANENTLY` (Constitutional violation) |

---

## 4. Job State Machine

```
                 +-------------+
                 |   CREATED   |
                 +-------------+
                        │
                        v
                 +-------------+
                 |   QUEUED    |
                 +-------------+
                   /         \
   Policy Requires             Resources
      Approval                 Available
         /                         \
        v                           v
+------------------+         +-------------+
| WAITING_APPROVAL |         |   RUNNING   | <-------+
+------------------+         +-------------+         │
        │                           │                 │
  Human Approves             Pause / Interrupted     Resume
        │                           │                 │
        v                           v                 │
   (to QUEUED)               +-------------+         │
                             |   PAUSED    | ────────+
                             +-------------+
                                    │
               +--------------------+--------------------+
               │                    │                    │
          Process Exits       Process Exits       Timeout / Signal
             Code 0              Code != 0             Cancel
               │                    │                    │
               v                    v                    v
        +-------------+      +-------------+      +-------------+
        |  SUCCEEDED  |      |   FAILED    |      |  CANCELLED  |
        +-------------+      +-------------+      +-------------+
```

---

## 5. Official MCP Tasks Status & Long-Running Operations

As verified in the Phase 1.5 audit:
- The experimental MCP Tasks extension is **deliberately absent from the official Python SDK v2.2.0**.
- **TACP will not fake or invent synthetic MCP Tasks protocol messages**.
- Long-running operations are managed via TACP's internal Job System and exposed through standard MCP tools:
  - `tacp_job_create(contract) -> job_id`
  - `tacp_job_status(job_id) -> JobStatus`
  - `tacp_job_logs(job_id, offset, limit) -> logs`
  - `tacp_job_cancel(job_id) -> bool`
