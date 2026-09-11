# TACP Resource Model Specification
## Bounded Limits, Watchdog Timers & Empirical Android Reality

- **Standard:** TACP-SPEC-004-RESOURCE
- **Status:** APPROVED SPECIFICATION (GATE A)
- **Phase:** Phase 4 — Controlled Command Execution
- **Target OS:** Android 13 / Termux (aarch64)

---

## 1. Constitutional Truth: Hard Controls vs. Best-Effort Governance

A core requirement of TACP is empirical accuracy in security claims:
> **"Never claim a hard kernel or hardware sandbox when only application-level enforcement is available."**

On modern desktop Linux distributions (Ubuntu, Fedora), container engines (Docker, Podman, systemd) rely on root privileges to configure **cgroups v2**, **seccomp-bpf**, and **user namespaces**.

On Android within Termux:
1. The app executes as an unprivileged Linux UID (e.g. `u0_a316`).
2. `/sys/fs/cgroup` is mounted read-only and restricted to the Android OS framework (`system_server`).
3. User processes **cannot** create, modify, or assign cgroup resource limits.
4. Android's Bionic C library and `jemalloc` allocator frequently behave unpredictably when subject to standard POSIX `setrlimit(RLIMIT_AS, ...)` (often crashing initialization routines before `main()`).

Therefore, TACP explicitly delineates its resource model into **HARD GUARANTEES** and **BEST-EFFORT GOVERNANCE**.

---

## 2. Resource Enforcement Classification

```
+---------------------------------------------------------------------------------+
|                       RESOURCE ENFORCEMENT CLASSIFICATION                       |
+---------------------+-------------------------+---------------------------------+
| Resource Dimension  | Mechanism               | Enforcement Guarantee           |
+---------------------+-------------------------+---------------------------------+
| Execution Duration  | Watchdog Timer + killpg | HARD GUARANTEE                  |
| Stdout Stream Cap   | Bounded Pipe Reader     | HARD GUARANTEE                  |
| Stderr Stream Cap   | Bounded Pipe Reader     | HARD GUARANTEE                  |
| Argv Vector Bounds  | Pre-Spawn Validation    | HARD GUARANTEE                  |
| Env Payload Bounds  | Pre-Spawn Validation    | HARD GUARANTEE                  |
| Concurrency Bounds  | SQLite Write Lock       | HARD GUARANTEE                  |
| CPU Usage           | Time Slice / Watchdog   | BEST-EFFORT (Watchdog bounded)  |
| Memory Usage        | Output cap + Watchdog   | BEST-EFFORT (OS LMK Dependent)  |
| Disk Write Quotas   | Workspace Jailing       | BEST-EFFORT (Containment only)  |
+---------------------+-------------------------+---------------------------------+
```

---

## 3. Detailed Hard Guarantees

### 1. Execution Duration (Watchdog Timeout)
- Every execution is governed by a monotonic watchdog timer.
- Default duration: 15 seconds.
- Maximum allowable limit: 60 seconds.
- Enforcement: When `monotonic_now - start_time >= timeout_seconds`, the supervisor enters the termination sequence (`SIGTERM` -> 1.5s grace period -> `SIGKILL` to `PGID`). The process group cannot survive beyond `timeout + 1.5s`.

### 2. Standard Output Streams (Stdout / Stderr Byte Caps)
- Streams are read into memory chunks via non-blocking I/O.
- Hard byte limit: 64 KB (65,536 bytes) per stream.
- When the buffer reaches 65,536 bytes:
  - Reading stops.
  - Remaining output is drained to `/dev/null` or discarded.
  - The `stdout_truncated` or `stderr_truncated` flag is set to `True`.
  - Memory consumption in TACP for stream capture is strictly bounded to $\le 128\text{ KB}$.

### 3. Argument Vector & Environment Size Caps
- Maximum argument count: 64 elements.
- Maximum argument string length: 4,096 bytes per argument.
- Maximum caller environment variables: 16 variables.
- Maximum environment variable value length: 2,048 bytes.
- Total argument payload size: $\le 65,536$ bytes.
- Requests exceeding these boundaries are rejected in Stage 1 before any process is spawned.

---

## 4. Detailed Best-Effort Controls & Android Realities

### 1. CPU Quotas
- Because cgroup CPU controllers (`cpu.max`) are inaccessible without Android root, TACP does not claim hard fractional CPU throttling (e.g. "cap process to 25% CPU core").
- Instead, CPU abuse is mitigated by **hard wall-clock timeouts**. A 100% CPU spinning loop cannot run longer than the configured timeout (e.g. 15s).

### 2. Memory Limits
- POSIX `setrlimit(RLIMIT_DATA)` or `RLIMIT_AS` on Android Bionic can cause premature crashes in linker relocations.
- Memory protection relies on:
  - Output stream bounding (preventing memory amplification in TACP).
  - Watchdog timeouts.
  - Android's native kernel Out-Of-Memory (OOM) killer and Low Memory Killer Daemon (`lmkd`), which terminates rogue memory hogs.

### 3. Disk Space
- TACP does not implement a simulated kernel block quota.
- Protection relies on jailing writes strictly within the designated workspace root directory and cleaning up temporary files.
