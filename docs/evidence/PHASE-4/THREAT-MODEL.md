# Phase 4 Evidence — Threat Model

**Document ID**: TACP-EV-P4-03  
**Status**: VERIFIED  
**Target Release**: v0.4.0-rc.1  

## 1. Threat Categories & Defenses

| Threat ID | Threat Vector | Attack Scenario | TACP Mitigation | Verified By |
|---|---|---|---|---|
| TM-01 | Shell Injection | `cmd; rm -rf /`, `| cat`, `$(id)` | Direct `execve` via `subprocess.Popen(shell=False)` with structured `argv: Tuple[str, ...]`. Zero shell interpretation. | SEC-01 to SEC-16 |
| TM-02 | Path Poisoning | Prepending `.` or untrusted dirs to `PATH` | Curated safe `PATH` resolution; callers strictly cannot override `PATH`. | SEC-17 to SEC-19 |
| TM-03 | Path Traversal | `../../bin/sh` or symlink evasion | Canonical `Path.resolve()` check against forbidden binaries and whitelist. | SEC-20 to SEC-24 |
| TM-04 | Environment Smuggling | `LD_PRELOAD`, `PYTHONPATH`, API secrets | Aggressive regex pattern scrubbing (`BLACK_LISTED_ENV_PATTERNS`) and system variable protection. | SEC-25 to SEC-48 |
| TM-05 | File Descriptor Leakage | Inheriting open sockets, DB handles, pipes | `close_fds=True` unconditionally enforced on process spawn. | SEC-50 |
| TM-06 | Denial of Service / Flooding | Infinite loop, memory bomb, output flood | Watchdog timer (SIGTERM -> SIGKILL process group) and strict 64KB stream truncation buffers. | SEC-51 to SEC-55 |
| TM-07 | Process Escape / Orphans | Forking child processes that outlive parent | Process group isolation via `setsid` (`start_new_session=True`); `os.killpg(pgid)` slays entire process tree. | SEC-56 to SEC-60 |
| TM-08 | Approval Bypasses / Replay | Reusing token, parameter tampering | Single-use `verify_and_consume` bound to cryptographic SHA-256 `contract_hash`. | SEC-61 to SEC-74 |
| TM-09 | Terminal Injection | ANSI escape sequences (`\x1b[2J`, title bar leaks) | Authoritative regex scrubbing of ANSI escape sequences before returning stdout/stderr. | SEC-91 to SEC-94 |
