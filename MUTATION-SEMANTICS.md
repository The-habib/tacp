# TACP Mutation Semantics & Idempotency Specification

This document defines the formal mutation semantics, state transitions, idempotency guarantees, and conflict resolution rules for all mutating capabilities within the Termux AI Control Plane (TACP).

---

## 1. Mutation Taxonomy Matrix

| Capability | Idempotent | Precondition Check | State Mutation | Postcondition & Guarantees |
|---|---|---|---|---|
| `workspace.patch` | **Yes** (via OCC) | `base_checksum` matches target file SHA-256 | Atomic patch apply + snapshot creation | Target file SHA-256 equals `result_checksum` |
| `workspace.patch_batch` | **Yes** (via OCC) | All file checksums match before write | All-or-nothing transactional multi-file commit | All targets verified or full rollback applied |
| `filesystem.write` | **Yes** | Path inside workspace jail | Writes exact bytes to target path | File content exactly matches provided bytes |
| `filesystem.delete` | **Yes** | Path inside workspace jail | Removes target path if present | File/dir does not exist (success if already absent) |
| `filesystem.append` | **No** | Path inside workspace jail | Appends bytes to end of file | File size grows by length of appended bytes |
| `package.install` | **Yes** | APK path valid + signed | Calls package manager to install | Package is installed on device |
| `package.uninstall` | **Yes** | Package name valid | Removes package if present | Package is not installed (success if not present) |
| `setting.put` | **Yes** | Valid namespace + key | Updates system/secure/global setting | Setting value equals target value |
| `process.spawn` | **No** | Binary inside allowed path | Forks new PID in OS table | New independent process running |
| `process.kill` | **Yes** | Target PID exists | Sends SIGTERM / SIGKILL | PID is terminated (success if already gone) |
| `input.tap` / `input.key`| **No** | Screen on / UI active | Injects touch/key event into window | UI receives hardware input event |

---

## 2. State Machine Diagrams

### 2.1 Idempotent Optimistic Concurrency Patch Flow (`workspace.patch`)

```text
[Incoming Patch Request]
         │
         ▼
[Check Idempotency-Key] ──(Present & Completed)──► [Return Cached Result (_idempotent_replay: true)]
         │ (Absent or New)
         ▼
[Verify base_checksum vs Disk SHA-256]
         │
         ├──(Checksum Mismatch)──► [Abort with CONFLICT (HTTP 409)]
         │
         ▼ (Checksum Matches)
[Acquire MUTATION Admission Lane Slot]
         │
         ▼
[Create Atomic Snapshot in ~/.tacp/snapshots]
         │
         ▼
[Apply Unified Diff via In-Memory Buffer]
         │
         ▼
[Verify Result SHA-256 vs Header]
         │
         ├──(Validation Failed)──► [Rollback from Snapshot & Raise PATCH_INVALID]
         │
         ▼ (Validation Passed)
[Commit to Disk + SQLite patches table]
         │
         ▼
[Invalidate State Cache ('storage')]
         │
         ▼
[Record AuditEvent in Hash Chain]
         │
         ▼
[Store Idempotency Record (Status: COMPLETED)]
```

---

## 3. Idempotency Key Semantics

Clients and autonomous agents can include an `idempotency_key` parameter (or `Idempotency-Key` HTTP header) with any mutating request.

1. **Replay Detection:**
   - When a request with an existing `idempotency_key` is received, TACP computes the SHA-256 hash of the parameters.
   - If the parameters match and the operation already succeeded, TACP immediately returns the cached result with `_idempotent_replay: true`.
   - **Zero side-effects are re-executed.**
2. **Conflict Prevention:**
   - If the same `idempotency_key` is sent with different parameters, TACP rejects the request with code `CONFLICT`.
   - If a concurrent request with the same key is already in-flight, subsequent requests fail fast with code `CONFLICT`.
3. **TTL & Persistence:**
   - Idempotency records are cached in memory and expire after 1 hour (3,600s).
