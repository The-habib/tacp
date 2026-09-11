# Phase 2 — Vertical Slice 2: Implementation Report
## Governed Workspace Multi-File Patch (`workspace.patch_batch`)

- **Capability:** `workspace.patch_batch`
- **Release Target:** `v0.3.0-rc.1`
- **Specification:** TACP Phase 2.5 + Gate C Directive
- **Status:** **COMPLETE & VERIFIED**

---

## 1. Architectural Design & Implementation

Vertical Slice 2 introduces the capability to atomically apply unified diff patches to multiple text files within an authorized workspace root.

### Core Modules Implemented:
1. **Domain Models (`src/tacp/domain/patch.py`):**
   - `BatchPatchItem`: Encapsulates per-item `subpath`, `patch_content`, and `base_checksum`.
   - `BatchPatchResult`: Encapsulates `batch_id`, `status`, `changed_files`, `results`, `audit_id`, and `details`.

2. **Configuration & Resource Limits (`src/tacp/infrastructure/config.py`):**
   - Dual feature flags: `mutation_enabled` AND `batch_mutation_enabled` (both default to `False`).
   - Limits: `max_batch_files=10`, `max_batch_patch_total_bytes=1MB`, `max_batch_resulting_total_bytes=5MB`.

3. **Database Schema & Migrations (`src/tacp/infrastructure/migrations.py`):**
   - Migration 3: Created `batches` table tracking `batch_id`, `workspace_id`, `status`, `target_paths_json`, `snapshot_manifest_json`, `applied_at`, and `rolled_back_at`.

4. **Deterministic Multi-Resource Locking (`src/tacp/core/lock_service.py`):**
   - Implemented `hold_many` and `release_many` using lexicographical path sorting to prevent deadlocks (`lock_keys = sorted(f"{workspace_id}:{subpath}" ...)`).
   - Atomic rollback: if any lock acquisition fails or is contested, all acquired locks are released in reverse order.

5. **Canonical Batch Hashing (`src/tacp/control/approval.py`):**
   - `compute_canonical_batch_hash`: Deterministically normalizes CRLF -> LF, sorts items by subpath, and generates compact canonical SHA-256 JSON digest.
   - Wildcard target support: Scoped approval tickets support `target_path = "*"` bound to the canonical batch hash.

6. **Filesystem Provider (`src/tacp/providers/filesystem.py`):**
   - `apply_patch_batch`: 4-phase transaction (Preflight simulation -> Snapshots -> Temporary same-directory staging -> Atomic `os.replace` commit with post-write checksum verification).
   - All-or-nothing rollback: any failure during staging or commit immediately restores snapshots and unlinks temporary files.
   - `rollback_patch_batch`: Restores original files from archived snapshots.

7. **Governed Service Pipeline (`src/tacp/core/patch_service.py`):**
   - 16-stage pipeline execution: validation, duplicate target denial, policy evaluation, risk classification, lock acquisition, approval verification, execution, and audit logging.
   - Batch rollback and query APIs: `rollback_batch`, `list_batches`, `get_batch`.

8. **MCP Protocol Integration (`src/tacp/access/mcp/`):**
   - Tool `workspace.patch_batch` conditionally exposed only when dual flags are active.
   - Full MCP 2026-07-28 and 2024-11-05 compatibility verified via official `@modelcontextprotocol/inspector`.

9. **CLI Interface (`src/tacp/cli/main.py`):**
   - Added `tacp batch list`, `tacp batch show <id>`, and `tacp batch rollback <id>`.
   - Added `--allow-batch-mutation` flag to `tacp serve`.
