# Phase 4 Evidence — Process Model & Containment

**Document ID**: TACP-EV-P4-07  
**Status**: VERIFIED  
**Target Release**: v0.4.0-rc.1  

## 1. Process Lifecycle
- **Session Isolation**: Spawning uses `start_new_session=True` (`setsid()`), creating a new session and setting Process Group ID equal to the child PID (`PGID == PID`).
- **File Descriptors**: `close_fds=True` prevents leaking open sockets, database handles, and pipes from the TACP daemon.
- **Watchdog Timer**: Processes running beyond `timeout_seconds` (default 15s, hard cap 60s) are reaped.
- **Clean Escalation**: The watchdog sends `SIGTERM` to the entire process group (`os.killpg(pgid, signal.SIGTERM)`), waits 100ms for clean exit, then escalates to `os.killpg(pgid, signal.SIGKILL)` if any child persists.
- **Non-blocking Stream Readers**: I/O is bounded to 64KB per stream; excess output is marked `stdout_truncated=True` or `stderr_truncated=True`.
