# Phase 3 Evidence — Approval Engine & Token Security Audit

**Document ID**: TACP-EV-P3-05  
**Status**: VERIFIED  

## 1. Cryptographic Token Hashing
- Migration 4 added `token_hash` column and unique index `idx_approvals_token_hash`.
- Raw bearer token `tacp_appr_<hex>` is never stored in SQLite. Only `sha256(raw_token)` is persisted.
- Masked prefix (`tacp_appr_...`) is retained in `token` column for operator display only.

## 2. Approver Authority Checks
- `approve()` rejects approval by agent principals or principals with trust tier < `PRIVILEGED`.
- Self-approval by the requesting principal is explicitly forbidden.

## 3. Atomic Single-Use Consumption
- Ticket consumption is executed via atomic conditional update:
  `UPDATE approvals SET status = 'CONSUMED' WHERE token_hash = ? AND status = 'APPROVED'`
- Multi-threaded race test (`tests/unit/test_approval_concurrency.py`) with 10 concurrent threads confirms exactly 1 thread succeeds and 9 receive `APPROVAL_ALREADY_USED`.
