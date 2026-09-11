# TACP Phase 2: Vertical Slice 2 Adversarial Design Review

**Target:** Vertical Slice 2 Design (`workspace.patch_batch`)  
**Document Reviewed:** `docs/phases/SLICE-2-MULTI-FILE-PATCH-DESIGN.md`  
**Reviewers:** Lead Principal Architect & Independent Security Engineer  
**Date:** September 11, 2026  
**Status:** **APPROVED FOR IMPLEMENTATION**

---

## 1. Adversarial Challenges & Invariant Validations

### 1.1 Challenge: Partial Application & Crash Inconsistency
- **Threat**: If process crashes or receives `SIGKILL` after committing file 1 of 3, the filesystem is left in a partially mutated state.
- **Architectural Defense**:
  - TACP implements pre-flight verification so that all hunks and limits are validated before any target file is modified.
  - Sibling staging files (`.tacp_tmp_*`) are completely flushed and fsynced *before* the commit loop begins.
  - If a software-level failure occurs during the commit loop, the commit loop catches the error and restores previously committed files from pre-created snapshots.
  - In the event of catastrophic OS kill during the commit loop, the database record remains uncommitted/in-flight; subsequent startup/recovery detects the in-flight batch and notifies operator or initiates rollback reconciliation.

### 1.2 Challenge: Deadlock in Multi-Resource Locking
- **Threat**: Request A locks file 1 then file 2; concurrent Request B locks file 2 then file 1, causing cyclic wait (deadlock).
- **Architectural Defense**:
  - Canonical lexicographical sorting is enforced on normalized subpaths:
    `sorted_subpaths = sorted(set(normalized_subpaths))`
  - Locks are strictly acquired in ascending order. If any lock fails to acquire within timeout, all previously acquired locks are released in reverse order. Deadlock is impossible.

### 1.3 Challenge: Duplicate Target Aliasing
- **Threat**: Attacker submits a batch containing `"src/main.py"" and `"./src/main.py"" or `"src//main.py"" to bypass single-patch rules.
- **Architectural Defense**:
  - Paths are normalized (`replace("\\", "/")`, split, resolve components). If normalized paths contain duplicates, the entire batch is rejected during pre-flight with `VALIDATION_ERROR`.

### 1.4 Challenge: Batch Hash Canonicalization
- **Threat**: Two semantically different patch batches could yield the same hash if keys or file order vary in JSON serialization.
- **Architectural Defense**:
  - Canonical dictionary structure with sorted keys and sorted items:
    ```python
    canonical_items = sorted(
        [
            {
                "base_checksum": p["base_checksum"].strip().lower(),
                "patch_content": p["patch_content"],
                "subpath": clean_subpath(p["subpath"]),
            }
            for p in patches
        ],
        key=lambda x: x["subpath"],
    )
    canonical_bytes = json.dumps(canonical_items, sort_keys=True, separators=(",", ":")).encode("utf-8")
    batch_hash = hashlib.sha256(canonical_bytes).hexdigest()
    ```

---

## 2. Review Sign-Off Matrix

| Dimension | Assessment | Notes | Status |
| :--- | :--- | :--- | :---: |
| **Atomicity** | Strong all-or-nothing guarantee | Preflight + staging + rollback on commit error | **PASS** |
| **Deadlock Safety** | Deterministic ordering | Sorted path lock acquisition | **PASS** |
| **OCC Concurrency** | Per-file base checksum validation | Stale diff on any file halts entire batch | **PASS** |
| **Approval Scope** | Canonical batch hash + metadata targets | Replay and tampering defeated | **PASS** |
| **Storage Safety** | Same-directory temp files + fsync | Zero cross-mount `EXDEV` risk | **PASS** |
| **Scope Bounds** | Pure text modification | No delete, no rename, no exec | **PASS** |

**Design Review Decision: PROCEED TO IMPLEMENTATION.**
