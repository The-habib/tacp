# Phase 3 Evidence — Identity and Principal Model Audit

**Document ID**: TACP-EV-P3-04  
**Status**: VERIFIED  

## 1. Principal Architecture
- **PrincipalType**: `AGENT`, `HUMAN`, `SYSTEM`
- **TrustTier**: `UNTRUSTED`, `RESTRICTED`, `PRIVILEGED`
- **CredentialSource**: `LOCAL_STDIO`, `TOKEN`, `SYSTEM`, `NONE`

## 2. Context Invariants
- `RequestContext` mandates `request_id`, `trace_id`, `principal`, and `capability`.
- Context is immutably threaded from MCP dispatch or CLI invocation down to service execution, policy enforcement, locking, and audit recording.

## 3. Privilege Escalation Defenses
- Self-approval by agent principals is blocked by `ApprovalEngine`.
- Restricted or untrusted principals cannot approve tickets.
- Bearer tokens are decoupled from identity; authorization requires valid ticket hash AND authority check.
