# Phase 3 Evidence — Rollback Governance & Snapshot Audit

**Document ID**: TACP-EV-P3-07  
**Status**: VERIFIED  

## 1. Capability Registration
- Registered `workspace.rollback` and `workspace.batch_rollback` as mutating capabilities.
- Evaluated under `PolicyEngine` with full audit event generation.

## 2. Authorization Rules
- Rollback by `agent` requires explicit human approval ticket.
- Rollback by `operator` / `human_operator` (privileged tier) is allowed immediately.

## 3. Snapshot Permissions & Restoration
- Snapshot directories restricted to mode `0700` and snapshot files to mode `0600`.
- Optimistic concurrency control verifies target file checksum matches expected post-patch state prior to rollback.
- Atomic replacement in same parent directory prevents partial rollbacks.
