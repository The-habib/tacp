# TACP Patch Engine & Workspace Mutation Specification

**Document:** `docs/execution/PATCH-MODEL.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**Execution Lead:** Antigravity Principal Execution Engineer  
**Date:** September 11, 2026  

---

## 1. Why `workspace.patch` Precedes `fs.write`

In conventional, ungoverned AI tools, an agent is often given raw `fs.write(path, full_content)`. This pattern introduces catastrophic risks:
- An agent truncates a 2,000-line file to 50 lines due to context length limits.
- An agent silently overwrites changes made concurrently by a human developer.
- An agent introduces syntax errors with zero auditability or pre-execution diff review.

TACP Phase 2 establishes **`workspace.patch`** as the foundational mutation primitive:
1. **Explainable Before Application**: Generates a clear, reviewable unified diff before touching storage.
2. **Optimistic Concurrency Control**: Requires and verifies `base_checksum` (SHA-256 of target file before mutation).
3. **Atomic Patching**: Applies changes using atomic file staging; any failure leaves the original file 100% intact.
4. **Structured Result**: Returns before/after checksums, lines changed, and verification status.

---

## 2. The Patch Data Model

```python
@dataclass(frozen=True)
class WorkspacePatch:
    patch_id: str  # Unique UUIDv4
    workspace_id: str  # Target registered workspace ID
    subpath: str  # Canonical relative file path (e.g. "src/main.py")
    base_checksum: str  # Expected SHA-256 before patch
    patch_content: str  # Unified diff or structured hunk
    dry_run: bool  # If true, simulate and explain without writing
    author_principal: Principal  # Originating actor
    risk_level: RiskLevel  # Evaluated risk (typically R2)
    approval_id: Optional[str]  # Required if risk exceeds autonomy ceiling
    created_at: datetime  # Timestamp of patch proposal
```

### Database Persistence Schema
```sql
CREATE TABLE IF NOT EXISTS patches (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    subpath TEXT NOT NULL,
    base_checksum TEXT NOT NULL,
    after_checksum TEXT,
    patch_diff TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PROPOSED', 'APPLIED', 'CONFLICT', 'DENIED', 'FAILED', 'ROLLED_BACK')),
    lines_added INTEGER NOT NULL DEFAULT 0,
    lines_removed INTEGER NOT NULL DEFAULT 0,
    applied_at TEXT,
    principal_id TEXT NOT NULL,
    approval_id TEXT,
    FOREIGN KEY(workspace_id) REFERENCES workspaces(id),
    FOREIGN KEY(principal_id) REFERENCES principals(id)
);

CREATE INDEX IF NOT EXISTS idx_patches_ws ON patches(workspace_id, subpath);
```

---

## 3. Patch Execution Pipeline (First Vertical Slice)

```
[1. Inbound workspace.patch Request]
              │
              v
[2. Control Plane Validation]
      ├── Workspace active?
      ├── Subpath resolves inside jail?
      ├── Target not in SECRET_FILENAMES?
      └── Policy permits?
              │
              v
[3. Concurrency Check (Base Checksum)]
      ├── Read target file current bytes
      ├── Compute sha256(current_bytes)
      └── IF sha256 != base_checksum:
             ABORT with ErrorCode.CONFLICT ("File changed on disk")
              │
              v
[4. Patch Dry-Run / Simulation]
      ├── Apply diff in-memory to current bytes
      ├── If syntax/hunk error: ABORT with ErrorCode.PATCH_FAILED
      └── Compute predicted after_checksum
              │
      ├── IF request.dry_run == True:
             RETURN status="SIMULATED", diff=preview, after_checksum=predicted
              │
              v
[5. Backup / Snapshot Creation]
      └── Copy current file to ~/.tacp/snapshots/{patch_id}/
              │
              v
[6. Atomic Disk Write]
      ├── Write patched bytes to .tacp_tmp_{uuid} in same directory
      ├── Call os.fsync(fd)
      └── os.replace(temp_path, target_path)
              │
              v
[7. Post-Verification]
      ├── Read target_path from disk
      ├── Assert sha256(disk_bytes) == predicted after_checksum
      └── If mismatch: Rollback from snapshot; ABORT with ErrorCode.VERIFICATION_FAILED
              │
              v
[8. Audit & Return]
      ├── Record AuditEvent with before/after checksums and patch_id
      └── RETURN status="APPLIED", patch_id=id, after_checksum=post_hash
```

---

## 4. Possible Results & Error Taxonomy

| Result Code | Meaning | Recovery Action |
|---|---|---|
| `APPLIED` | Patch succeeded and verified on disk | Normal operation |
| `SIMULATED`| Dry-run successful; no disk changes made | Caller can proceed with real patch |
| `CONFLICT` | Target file modified since `base_checksum` | Caller must re-read file and rebase diff |
| `APPROVAL_REQUIRED` | Risk exceeds agent autonomy ceiling | Caller must wait for human approval |
| `DENIED` | Target file is secret or policy blocks mutation | Operation rejected |
| `FAILED` | Patch hunk failed to apply or syntax error | Caller must correct diff |
| `ROLLED_BACK` | Write or verification failed; restored snapshot | System safely restored to original state |
