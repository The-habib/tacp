# TACP Phase 2: Vertical Slice 2 Design Specification
## Multi-File Governed Workspace Patch (`workspace.patch_batch`)

**Capability:** `workspace.patch_batch`  
**Target Release:** `v0.3.0-rc.1`  
**Scope:** Multi-file text modification within a single authorized workspace.  
**Constitutional Invariant:** "AI may be autonomous, but AI must never be sovereign."

---

## 1. Scope & Bounded Operations

Vertical Slice 2 extends TACP from single-file modification to atomic multi-file patching across a single workspace.

### Permitted Operations:
- **MODIFY existing text files** within the authorized workspace jail via unified diffs.

### Explicitly Forbidden Operations (Hard Bounds):
- **NO file deletion** (`rm`, `unlink`).
- **NO arbitrary file creation** (creation without diff or outside authorized workspace).
- **NO file renaming / moving** (`mv`, `rename`).
- **NO permission modification** (`chmod`, `chown`).
- **NO executable flag manipulation**.
- **NO shell execution** (`subprocess`, `exec`).
- **NO Android device mutation**.

---

## 2. 16-Stage Governed Pipeline for Batch Execution

Every multi-file patch request must traverse all 16 stages as an indivisible unit:

```
1. MCP Protocol (`workspace.patch_batch`)
   ↓
2. App Service Routing (`ToolRegistry._dispatch`)
   ↓
3. Identity Resolution (Authenticated `Principal`)
   ↓
4. Capability Check (`workspace.patch_batch` registered)
   ↓
5. Resource Resolution (`WorkspaceService.get_workspace`)
   ↓
6. Input Validation (Jail, duplicate targets, UTF-8, bounds)
   ↓
7. Policy Enforcement (`batch_mutation_enabled`, protected patterns)
   ↓
8. Risk Evaluation (Classified as `R2` live, `R1` dry-run)
   ↓
9. Budget & Limits (Per-file & aggregate batch limits)
   ↓
10. Lock Acquisition (Deterministic lexicographical path order)
   ↓
11. Approval Verification (Canonical batch hash binding, single-use)
   ↓
12. Execution Contract Issuance (Formal batch contract)
   ↓
13. Provider Staging & Atomic Commit (Snapshots, sibling temp files, atomic replace)
   ↓
14. Observation & Postcondition Check (Verify all files on disk)
   ↓
15. Sanitization (Redact tokens & secrets)
   ↓
16. Audit Logging (Single atomic batch audit event)
```

---

## 3. Batch Atomicity & Failure Semantics

Batch modification is strictly **all-or-nothing**:

### 3.1 Preflight Phase (Read-Only)
1. **Target Validation**: Each file in the batch must resolve within the workspace jail, cannot be a symlink, and cannot match protected resource patterns (`.git`, `.tacp`, `.env`, keys).
2. **Duplicate Target Detection**: No two patch items may target the same canonical relative subpath.
3. **Optimistic Concurrency Control**: For every file, current disk bytes are read and SHA-256 checksum is compared against caller-provided `base_checksum`. If ANY file mismatches, abort immediately with `CONFLICT`.
4. **Hunk Simulation**: Unified diff hunks for every file are parsed and applied in-memory. If any hunk fails to match or resulting file size exceeds limits, abort immediately with `VALIDATION_ERROR`.
5. **No disk modification occurs during preflight.**

### 3.2 Staging Phase
1. For every target file, save a pre-mutation snapshot in `~/.tacp/snapshots/{batch_id}/{subpath}`.
2. For every target file, write patched contents into a temporary sibling file:
   `{target.parent}/.tacp_tmp_{uuid}`
3. Flush and call `os.fsync(f.fileno())` on each temporary staging file.

### 3.3 Commit Phase
1. Iterate through staged files and commit each via POSIX `os.replace(temp_file, target)`.
2. **Commit Failure Recovery**: If an unexpected filesystem I/O error or OS failure interrupts the commit loop at file $ of $:
   - An immediate automatic rollback is triggered for already-committed files  \dots k-1$ using their archived snapshots.
   - Any uncommitted staging files ( \dots N$) are unlinked.
   - System records a critical failure in the audit log and raises `TacpSecurityError(ErrorCode.ROLLBACK_FAILED)`.

---

## 4. Batch Approval & Canonical Hash Binding

### 4.1 Canonical Batch Structure
To prevent ambiguity or ordering attacks, the batch payload is canonicalized:
1. All patch items are sorted lexicographically by `subpath.strip().lstrip("./")`.
2. A canonical JSON structure is constructed:
   ```json
   [
     {"base_checksum": "...", "patch_content": "...", "subpath": "src/a.py"},
     {"base_checksum": "...", "patch_content": "...", "subpath": "src/b.py"}
   ]
   ```
3. `batch_hash` = `SHA-256(canonical_json.encode("utf-8"))`.

### 4.2 Approval Scope Invariants
The `ApprovalTicket` binds:
- `principal_id` (authenticated caller)
- `action_type = "workspace.patch_batch""
- `workspace_id`
- `target_path = "[batch:N_files]""
- `patch_hash = batch_hash` (canonical batch SHA-256)
- `metadata["targets"] = ["src/a.py", "src/b.py"]`
- `metadata["base_checksums"] = {"src/a.py": "...", "src/b.py": "..."}`
- `status = PENDING -> APPROVED -> CONSUMED` (single-use atomic transition).

---

## 5. Deadlock Prevention & Concurrency

When locking multiple resources, deadlock is mathematically prevented by **global deterministic ordering**:

1. Normalize all target subpaths.
2. Sort subpaths lexicographically:  < P_2 < \dots < P_N$.
3. Acquire resource locks sequentially in sorted order:
   `resource_id = f"{workspace_id}:{P_i}"`
4. If any lock acquisition fails (timeout / held by another process):
   - Immediately release all previously acquired locks in reverse order.
   - Raise `TacpSecurityError(ErrorCode.RESOURCE_LOCKED)`.

---

## 6. Resource Limits for Termux / Mobile Host

To prevent memory exhaustion and runaway lock contention on mobile devices:
- `max_batch_files`: **10 files**
- `max_patch_bytes`: **256 KB** per file (262,144 bytes)
- `max_batch_patch_total_bytes`: **1 MB** total diffs (1,048,576 bytes)
- `max_file_size_bytes`: **1 MB** per existing file (1,048,576 bytes)
- `max_batch_resulting_total_bytes`: **5 MB** total resulting bytes (5,242,880 bytes)
- `lock_ttl_seconds`: **45 seconds** for batch operations

---

## 7. Feature Flags & Gating

Two independent feature flags must be active:
1. `mutation_enabled = true` (Master mutation gate)
2. `batch_mutation_enabled = true` (Batch mutation gate)

If either flag is `false`:
- `workspace.patch_batch` is hidden from MCP `tools/list`.
- Any direct call is denied with `POLICY_DENIED`.

Environment variable:
```bash
export TACP_MUTATION_ENABLED=1
export TACP_BATCH_MUTATION_ENABLED=1
```
CLI argument:
```bash
tacp serve --allow-mutation --allow-batch-mutation
```

---

## 8. Rollback Engine for Batch Operations

`rollback_batch(batch_id)`:
1. Retrieve batch metadata and file list from database.
2. Verify all modified files still exist on disk.
3. Verify each file's current disk checksum matches the recorded `after_checksum`.
4. If ANY file was modified after the batch, halt with `CONFLICT` to prevent overwriting third-party changes.
5. Sequentially restore each file from snapshot using same-directory atomic temp replace.
6. Record audit event and update batch status to `ROLLED_BACK`.
