# Phase 4 Evidence — Policy Engine Architecture

**Document ID**: TACP-EV-P4-05  
**Status**: VERIFIED  
**Target Release**: v0.4.0-rc.1  

## 1. Governance Rules
`PolicyEngine` enforces capability access rules for execution:
1. `execution_enabled`: When `False` (default), all execution requests are denied unconditionally with `TacpSecurityError(ErrorCode.POLICY_DENIED)`.
2. `read_only_enforced`: Execution is classified as an active side-effect operation and blocked in read-only mode unless explicitly overridden with `--allow-execution`.
3. `network_enabled`: When `False`, any network-bearing command contracts are rejected.
4. `remote_execution_enabled`: Strictly disabled (`False`).

## 2. Risk Classification
- Commands are assigned a risk level:
  - `SAFE`: Non-destructive queries (`true`).
  - `CONTROLLED`: Standard governed commands (`printf`, `echo`).
  - `DANGEROUS`: Shells and interpreters (blocked unconditionally in Slice 1).
  - `CRITICAL`: System-altering utilities (`dd`, `mkfs`, `sudo`, `kill`) (permanently forbidden).
