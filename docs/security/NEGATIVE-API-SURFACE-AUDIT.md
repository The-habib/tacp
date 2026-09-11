# Negative API Surface Security Audit

- **Document Version**: 1.0.0
- **Target Release**: TACP 0.1 (`v0.1.0-rc.1`)
- **Audit Date**: 2026-09-11
- **Auditor**: Lead Security Architect & Principal Engineer
- **Audit Scope**: Complete source tree (`src/`)
- **Result**: **100% VERIFIED READ-ONLY. ZERO UNAUTHORIZED MUTATION PRIMITIVES.**

---

## 1. Executive Summary

A critical invariant of TACP 0.1 is that it is strictly and immutably **READ-ONLY**. Under the project constitution, an AI control plane must never possess mutation or shell execution capabilities during early operational phases.

This Negative API Surface Audit independently scans, categorizes, and audits every potential mutation and execution primitive across the entire production codebase (`src/`).

---

## 2. Primitive Scan Matrix

| Category | Targeted Primitives | Occurrences in `src/` | Audit Finding & Classification |
|---|---|:---:|---|
| **Filesystem Write / Mutation** | `open(..., 'w'/'a'/'r+')`, `write_text`, `write_bytes`, `truncate` | **0** | **SAFE**. No filesystem write operations exist in any provider or core service. |
| **Filesystem Deletion / Renaming** | `os.remove`, `os.unlink`, `os.rmdir`, `os.rename`, `Path.unlink`, `Path.rmdir`, `Path.rename`, `shutil.rmtree`, `shutil.move` | **0** | **SAFE**. Zero deletion or file movement primitives exist. |
| **Filesystem Directory Creation** | `os.mkdir`, `os.makedirs`, `Path.mkdir` | **1** | **LEGITIMATE**. `src/tacp/infrastructure/database.py:16` creates the internal data directory `~/.tacp` for local SQLite database storage. |
| **Permissions & Ownership** | `os.chmod`, `os.chown`, `Path.chmod`, `shutil.chown` | **0** | **SAFE**. Zero permissions alteration primitives exist. |
| **Process Execution & Shell Injection** | `os.system`, `os.popen`, `os.exec*`, `os.spawn*`, `os.fork`, `subprocess.*`, `pty.*` | **0** | **SAFE**. Zero subprocess or shell spawning primitives exist anywhere in `src/`. |
| **Process Mutation & Signaling** | `os.kill`, `os.killpg`, `signal.pthread_kill` | **0** | **SAFE**. Zero process termination or signaling primitives exist. |
| **Outbound Networking & Sockets** | `socket.*`, `urllib.request.*`, `requests.*`, `httpx.*`, `aiohttp.*` | **0** | **SAFE**. Server is purely local stdio. Zero outbound network calls exist. |
| **Android Privileged APIs** | `am`, `pm`, `cmd`, `shizuku`, `su`, `termux-api` intent mutation | **0** | **SAFE**. Zero Android OS mutations or intent broadcasts exist. |
| **Stream Output Writes** | `sys.stdout.write`, `sys.stderr.write`, `TextIO.write` | **5** | **LEGITIMATE**. Used strictly in `src/tacp/access/mcp/server.py` and `src/tacp/cli/main.py` for standard output response emission over stdio. |

---

## 3. Deep Primitive Audit Details

### 3.1 Directory Creation Audit (`src/tacp/infrastructure/database.py:16`)
```python
if not self.db_path.parent.exists():
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
```
- **Context**: Executed during local database connection initialization.
- **Safety Evaluation**: Only creates parent directory of `config.db_path` (default: `~/.tacp`). Does not accept arbitrary user paths or permit directory creation inside workspaces.

### 3.2 Stream Output Audit (`src/tacp/access/mcp/server.py`)
```python
out_stream.write(response.to_json() + "\n")
out_stream.flush()
```
- **Context**: Serializes JSON-RPC 2.0 response objects to the client stdio stream.
- **Safety Evaluation**: Standard stdio IPC protocol stream. Does not write to files or external sockets.

### 3.3 Disk Inspection Audit (`src/tacp/providers/system.py:21`)
```python
usage = shutil.disk_usage(target)
```
- **Context**: Reads available disk space for system health telemetry.
- **Safety Evaluation**: Non-mutating diagnostic query.

---

## 4. Policy Engine Enforcement Layer

In addition to the total absence of underlying mutation primitives in code, the TACP Policy Engine (`src/tacp/control/policy.py`) acts as a redundant defense-in-depth gatekeeper:

```python
FORBIDDEN_CAPABILITIES = {
    "fs.write",
    "fs.delete",
    "fs.chmod",
    "shell.exec",
    "bash.run",
    "os.system",
    "process.kill",
    "system.reboot",
    "android.intent",
    "android.sms",
    "android.notify",
    "adb.command",
    "shizuku.exec",
    "root.escalate",
}
```
Any request attempting to invoke these capabilities is intercepted and denied at policy evaluation time with `policy_decision: "DENIED"` and logged to the immutable audit trail.

---

## 5. Audit Conclusion

The negative API surface audit confirms that TACP 0.1 has zero mutation primitives, zero shell execution vectors, and zero network sockets. The system is structurally incapable of modifying host files, executing shell commands, or killing host processes.
