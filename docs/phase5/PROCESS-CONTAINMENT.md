# TACP Phase 5: Process Tree Security and PID Reuse Defense
**Document ID:** `TACP-PROC-SEC-001`  
**Classification:** Operating System Subsystem Architecture  
**Release Target:** v0.4.0-rc.1 Hardening / Phase 5  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Process Group Containment (`start_new_session=True`)

TACP executes all child processes using:
```python
subprocess.Popen(
    args=list(contract.argv),
    executable=contract.executable,
    cwd=contract.cwd,
    env=env,
    shell=False,
    start_new_session=True,  # Setsid: new process session and process group
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    close_fds=True,
)
```

### 1.1 Process Group Invariant
Because `start_new_session=True` triggers `setsid(2)` in the child process prior to `execve`:
- The child process becomes the leader of a new session.
- The child process becomes the leader of a new process group.
- The process group ID (`PGID`) is guaranteed equal to the child's `PID`.
- Signals delivered to negative PID (`-pgid` via `os.killpg`) propagate to all direct children, grandchildren, and descendants that remain in the session.

### 1.2 Termination Protocol
Process termination (timeout, cancellation, output flood, emergency stop) follows a strict two-stage escalation:
1. `os.killpg(pgid, signal.SIGTERM)`: Polite termination request allowing process clean-up.
2. Grace Period: Up to 1.5 seconds polling in 50ms intervals.
3. `os.killpg(pgid, signal.SIGKILL)`: Unconditional kernel-level process termination.

---

## 2. PID Reuse Defense

### 2.1 Threat Scenario
In Linux and Android kernels, PID values are recycled frequently (PID space typically 32,768 or 65,535).
If TACP stored `pgid` in SQLite and later received a `cancel_execution()` call:
- If the original process had long exited, the operating system might have reassigned that numeric PID to an innocent system daemon, keyboard service, or user app.
- Issuing `os.killpg(pgid, signal.SIGKILL)` blindly from historical database records would terminate unrelated processes!

### 2.2 Defensive Architecture: In-Memory Active Process Registry
In Phase 5, `ProcessExecutor` maintains an authoritative in-memory active registry:
```python
@dataclass(frozen=True)
class ActiveProcess:
    execution_id: str
    pid: int
    pgid: int
    start_mono: float
    start_time: float
```

- When `subprocess.Popen` returns, the process is registered in `_ACTIVE_PROCESSES[execution_id]`.
- When the execution reaps or terminates, the record is removed in the `finally:` block.
- **Invariant:** `cancel_execution()` and `emergency_stop()` will **only** dispatch OS signals to a PGID if the execution is actively tracked in `_ACTIVE_PROCESSES`.
- Untracked or historical database records log a warning and skip signal emission, completely neutralizing the PID reuse attack vector.
