# Phase 3 Evidence — Lock Service Concurrency & Ownership Audit

**Document ID**: TACP-EV-P3-06  
**Status**: VERIFIED  

## 1. Concurrency Model
- Implemented `BEGIN IMMEDIATE` transaction handling to serialize lock acquisition.
- Atomic purge of expired locks (`WHERE resource_id = ? AND expires_at <= ?`) inside write transaction.
- Atomic insert of new lock record; `sqlite3.IntegrityError` is translated to `TacpConflictError`.

## 2. Ownership & Token Binding
- `release_lock` strictly validates both `token` and `owner_id`. Foreign owners or stale tokens cannot release active locks.
- `refresh_lock` enables legitimate lock owners to extend lease TTL before expiration.
- Multi-threaded contention test (`tests/unit/test_lock_concurrency.py`) with 10 concurrent threads proves zero double-acquisition.
