# TACP Project Status

- **Current Phase**: Phase 3 — Execution Core Hardening & Security Gate (COMPLETE)
- **Last Updated**: 2026-09-11
- **Overall Status**: **PHASE 3 COMPLETE & VERIFIED — PRODUCTION EXECUTION CORE READY FOR PHASE 4**
- **Release Version**: `v0.3.1-rc.1` (`0.3.1rc1`)
- **Git Commit**: $(git rev-parse HEAD 2>/dev/null || echo "working-tree")

---

## 1. Verified Metrics & Health

- **Automated Tests**: **470 tests passing** (280 unit/integration + 190 security assertions).
- **Device Tests**: **7 tests passing** on physical Android 13 Termux `aarch64` hardware.
- **Code Coverage**: **84% authoritative coverage** across 2,484 Python statements.
- **Verification Pipeline**: `./verify` 7/7 deterministic stages **PASS**.
- **Supply Chain**: Zero known vulnerabilities via `pip-audit`.
- **Code Quality**: Ruff formatting, Ruff linting, and Mypy strict typing 100% clean.

---

## 2. Implemented & Verified Capabilities

### Read-Only Capabilities (13 Total)
1. `system.inspect`
2. `system.health`
3. `system.version`
4. `capabilities.list`
5. `workspace.list`
6. `workspace.inspect`
7. `fs.list`
8. `fs.stat`
9. `fs.read`
10. `fs.search`
11. `process.list`
12. `process.inspect`
13. `audit.recent`

### Governed Mutating Capabilities (4 Total)
1. `workspace.patch` (Single-file unified diff with snapshot rollback)
2. `workspace.patch_batch` (Multi-file atomic batch unified diffs)
3. `workspace.rollback` (Policy-governed single-file rollback)
4. `workspace.batch_rollback` (Policy-governed batch rollback)

---

## 3. Key Hardening Deliverables Completed

1. **Approval Engine & Preimage-Resistant Token Hashing**: Migration 4 deployed. Raw bearer tokens never stored in SQLite; only SHA-256 hashes are persisted. Multi-threaded race tests verify atomic single-use consumption.
2. **Lock Service Concurrency**: Upgraded to SQLite `BEGIN IMMEDIATE` transactions and atomic insert, eliminating TOCTOU races under contention. Added lease renewals via `refresh_lock`.
3. **Cryptographic Audit Hash Chain**: Migration 5 deployed. SHA-256 hash chaining anchored to an immutable 64-zero genesis. Proven detection against modified, deleted, or reordered records.
4. **Diff Parser Security**: Hardened against prefix corruption, hunk line count mismatches, and overlapping hunks. Verified with 100% differential testing against Python `difflib.unified_diff`.
5. **Database Thread Safety & WAL**: Thread-local SQLite connections with WAL mode, foreign keys, and 30s busy timeout. Tested safe recovery against file corruption.
6. **Supply Chain Pinning**: All GitHub Actions pinned to 40-character commit SHAs. Dependencies locked with `uv.lock`.
7. **Future Command Execution Design**: Complete specification in `docs/execution/COMMAND-EXECUTION-DESIGN.md` addressing all 17 security design questions. Zero implementation in Phase 3.

---

## 4. Next Phase Roadmap: Phase 4

- **Phase 4 Target**: Governed Command Execution Engine (`exec.run`).
- **Core Constraints**: Strict argv model, no shell interpretation, timeout guards, process group isolation (`os.setsid`), bounded I/O buffers, and human approval ticketing.
