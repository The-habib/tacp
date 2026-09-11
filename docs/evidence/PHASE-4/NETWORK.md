# Phase 4 Evidence — Network Containment Model

**Document ID**: TACP-EV-P4-09  
**Status**: VERIFIED  
**Target Release**: v0.4.0-rc.1  

## 1. Network Isolation Boundary
- `network_enabled` defaults to `False`.
- `ExecutionContract` contains explicit `network_enabled: bool` field, hashed into the canonical contract digest.
- Network utilities (`curl`, `wget`, `nc`, `ncat`, `netcat`, `socat`, `ssh`, `scp`, `rsync`) are explicitly enumerated in `FORBIDDEN_EXECUTABLE_NAMES` and rejected unconditionally.
- Package managers (`pkg`, `apt`, `pip`, `npm`, `cargo`, `gem`) that make network calls are forbidden.
- Remote process execution (`remote_execution_enabled`) is disabled.
