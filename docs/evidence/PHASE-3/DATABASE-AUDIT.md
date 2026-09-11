# Phase 3 Evidence — Database Integrity, Migrations & Tamper Audit

**Document ID**: TACP-EV-P3-09  
**Status**: VERIFIED  

## 1. Migration Sequence
1. Migration 1: Workspaces and base Audit Logs table
2. Migration 2: Principals, Policies, Approvals, Patches, Locks
3. Migration 3: Batches table
4. Migration 4: Approvals `token_hash` column and unique index
5. Migration 5: Audit logs `prev_hash` and `entry_hash` columns and index

## 2. Connection Concurrency
- `Database.connect()` uses `threading.local()` to ensure isolated thread-level SQLite connections.
- Enforces `PRAGMA journal_mode = WAL;`, `PRAGMA foreign_keys = ON;`, `PRAGMA busy_timeout = 30000;`.
- Tested against corruption: `Database.is_healthy()` safely returns `False` on corrupted database files without unhandled crashes.

## 3. Cryptographic Audit Hash Chain
- Hash chain uses SHA-256 over canonical JSON serialization of record fields linked to predecessor hash.
- Genesis anchor: `0` * 64.
- `AuditService.verify_integrity()` traverses entire chain.
- Proved with automated tests: Clean chain passes; modified record fails; deleted record fails; reordered records fail.
