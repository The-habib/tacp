# Phase 4 Evidence — Scoped Approval Engine

**Document ID**: TACP-EV-P4-06  
**Status**: VERIFIED  
**Target Release**: v0.4.0-rc.1  

## 1. Cryptographic Binding
Every non-dry-run execution request requires an approval ticket bound to:
- `principal_id`
- `action_type = "execution.request"`
- `workspace_id`
- `target_path = resolved_executable`
- `patch_hash = contract_hash` (the SHA-256 canonical hash of the full `ExecutionContract`)

## 2. Anti-Replay & Concurrency Controls
- **Single-Use Consumption**: `ApprovalEngine.verify_and_consume` transitions ticket state from `APPROVED` to `CONSUMED` in an atomic SQLite transaction (`BEGIN IMMEDIATE`).
- **Concurrent Races**: Tested under multi-threaded contention (SEC-73, SEC-74, sabotage tests). Exactly one consumer succeeds; all concurrent attempts fail closed.
- **TTL Expiry**: Tickets expire after 10 minutes (600 seconds). Expired tickets cannot be consumed or approved.
- **Token Hashing**: Bearer tokens (`tacp_appr_<hex>`) are stored as SHA-256 digests (`token_hash`) in the database; raw tokens are never persisted in plaintext.
