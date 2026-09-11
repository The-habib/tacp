# Phase 4 Evidence — Resource Governor & Limits

**Document ID**: TACP-EV-P4-08  
**Status**: VERIFIED  
**Target Release**: v0.4.0-rc.1  

## 1. Resource Limit Envelope
| Dimension | Enforced Limit | Violation Action |
|---|---|---|
| Max Execution Timeout | 15s (default), 60s (hard cap) | Watchdog process-group termination (`SIGKILL`) |
| Max Argv Length | 64 arguments | Rejected in Stage 1 with `TacpValidationError` |
| Max Single Arg Size | 4,096 bytes | Rejected in Stage 1 with `TacpValidationError` |
| Max Caller Environment Count | 16 entries | Rejected in Stage 7 with `TacpValidationError` |
| Max Single Env Value Size | 2,048 bytes | Rejected in Stage 7 with `TacpValidationError` |
| Max Stdout Stream Buffer | 65,536 bytes (64 KB) | Truncated with `stdout_truncated = True` |
| Max Stderr Stream Buffer | 65,536 bytes (64 KB) | Truncated with `stderr_truncated = True` |
| Max Concurrency | 1 active execution per workspace | Concurrency locked via `LockService` |
