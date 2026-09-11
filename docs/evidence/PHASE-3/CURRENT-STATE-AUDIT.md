# Phase 3 Evidence — Current State Audit

**Document ID**: TACP-EV-P3-01  
**Status**: VERIFIED  
**Commit**: $(git rev-parse HEAD 2>/dev/null || echo "working-tree")  
**Date**: $(date -u +"%Y-%m-%dT%H:%M:%SZ")  
**Scope**: Verification of pre-hardening claims vs verified reality.

## 1. Audit Findings Summary
An independent audit of the pre-Phase 3 repository revealed several discrepancies between documented claims and implementation:
1. **Approval Bearer Tokens**: Documented as secure, but raw tokens (`tacp_appr_<hex>`) were stored unhashed in SQLite.
   *Resolution*: Migration 4 and SHA-256 token hashing (`token_hash`) implemented. Raw tokens are never persisted.
2. **Lock Service Concurrency**: Under concurrent contention, `check_same_thread=False` on a shared connection caused cursor races and TOCTOU window between check and write.
   *Resolution*: Thread-local connections (`threading.local()`) and SQLite `BEGIN IMMEDIATE` + atomic `INSERT INTO locks` implemented.
3. **Rollback Governance**: `rollback_patch` and `rollback_batch` bypassed policy evaluation.
   *Resolution*: Enforced `workspace.rollback` and `workspace.batch_rollback` policy checks and audit logging.
4. **Unified Execution Pipeline**: MCP layer had redundant policy checks and disconnected request IDs.
   *Resolution*: Unified pipeline established where MCP delegates directly to `PatchService` with context and request IDs.
5. **Audit Hash Chain**: Claims of tamper evidence existed, but verification only checked JSON structure.
   *Resolution*: Migration 5 added `prev_hash` and `entry_hash` with SHA-256 hash chaining anchored to `0`*64 genesis.
6. **Version Drift**: Stale versions existed across files.
   *Resolution*: Unified single source of truth at `v0.3.1-rc.1` / `0.3.1rc1`.
