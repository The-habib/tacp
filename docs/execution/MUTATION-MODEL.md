# TACP Filesystem Mutation Safety & Atomic Operations

**Document:** `docs/execution/MUTATION-MODEL.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**Execution Lead:** Antigravity Principal Execution Engineer  
**Date:** September 11, 2026  

---

## 1. Mutation Philosophy

In TACP, **unrestricted, in-place filesystem mutation is forbidden**.

AI agents make mistakes, hallucinate syntax, and can be interrupted mid-stream by mobile OS process suspension or battery saving kills. Therefore, all mutations must be:
1. **Confined**: Bound strictly within an authorized, active workspace root.
2. **Atomic**: All-or-nothing changes via temporary file staging and atomic replacement.
3. **TOCTOU-Resistant**: Designed to withstand race conditions between Time-of-Check and Time-of-Use.
4. **Verified Post-State**: Validated immediately after write to prove integrity.

---

## 2. Path Security & Jailbreak Defenses

Every target path is canonicalized and verified against 15 specific attack classes:

| Attack Class | Attack Scenario | Defense Mechanism in TACP |
|---|---|---|
| **Basic Traversal** | `../secret.txt` | `Path.resolve()` canonicalization; verify starts with workspace root |
| **Deep Traversal** | `../../../../etc/passwd` | Canonicalization resolves to outside prefix; fails with `OUTSIDE_WORKSPACE` |
| **Absolute Path Escape** | `/data/data/com.termux/files/home/.bashrc` | Absolute paths stripped or asserted to match workspace root |
| **Mixed Separators** | `dir\\subdir/file` | POSIX normalization; reject non-standard separator injection |
| **Redundant Separators** | `dir///subdir//file` | Collapsed to single separator prior to canonical resolution |
| **Normalization Tricks** | `dir/./subdir/../file` | Full canonical resolution before permission checks |
| **Null Byte Injection** | `file.txt\0.png` | Scanned for `\0`; rejected with `TacpSecurityError(INVALID_PATH)` |
| **Symlink Escape** | `symlink -> /etc/shadow` | `os.path.realpath()` follows symlink; verifies resolved target within jail |
| **Nested Symlink Escape** | `link1 -> link2 -> /data` | Iterative resolution asserts every link hop remains inside jail |
| **Broken Symlink** | `link -> nonexistent` | Handled gracefully; does not cause unhandled crash |
| **Symlink Loop** | `linkA -> linkB -> linkA` | Loop detection with max hop limit (32 hops); aborts with error |
| **Sibling Workspace Escape** | `../workspace_b/file` | Confirmed distinct workspace root; blocked by jail check |
| **Prefix Collision** | `/home/ws` vs `/home/ws_evil` | Trailing slash boundary check (`/home/ws/` required) |
| **Unicode Edge Cases** | Normalization form C vs D | Canonicalized using Python `unicodedata.normalize('NFC', path)` |
| **Concurrent Path Race** | Directory swapped with symlink | File descriptor-based pinning or post-replace inode verification |

---

## 3. Time-of-Check vs. Time-of-Use (TOCTOU) Analysis

### The Problem
A malicious or concurrent process could alter a file between the moment TACP verifies its checksum/path and the moment TACP writes the replacement.

### The 5-Step TOCTOU-Resistant Pipeline
```
[1. RESOLVE]            --> Resolve canonical real path and verify jail confinement.
[2. AUTHORIZE]          --> Verify policy and compute base file SHA-256 checksum.
[3. STAGE ATOMICALLY]   --> Write new content into a unique hidden temp file in SAME directory:
                            target_dir / f".tacp_tmp_{uuid4().hex}"
[4. FSYNC TO STORAGE]   --> Call os.fsync(fd) to flush buffers to Android flash storage.
[5. ATOMIC RENAME]      --> Perform os.replace(temp_path, target_path) (POSIX atomic on same filesystem).
[6. POST-VERIFY]        --> Re-read target_path, verify post-checksum, and remove temp file if any error.
```

---

## 4. Atomic Replacement Implementation

```python
class AtomicFileWriter:
    @staticmethod
    def write_atomic(
        target_path: Path, content: str, expected_base_checksum: Optional[str] = None
    ) -> str:
        # Step 1: Check expected base state if file exists
        if target_path.exists():
            current_hash = hashlib.sha256(target_path.read_bytes()).hexdigest()
            if expected_base_checksum and current_hash != expected_base_checksum:
                raise TacpConflictError(
                    ErrorCode.CONFLICT,
                    f"File modified concurrently: expected {expected_base_checksum}, found {current_hash}",
                )

        # Step 2: Create temp file in same directory (ensures same filesystem for atomic rename)
        temp_path = target_path.parent / f".tacp_tmp_{uuid.uuid4().hex}"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())  # Ensure durable flash write

            # Step 3: Atomic replace
            os.replace(temp_path, target_path)

            # Step 4: Post-verification
            post_hash = hashlib.sha256(target_path.read_bytes()).hexdigest()
            return post_hash
        except Exception:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise
```

---

## 5. Failure Recovery & Interrupted Writes

1. **Power Cut / Crash during Write**: Data is written to `.tacp_tmp_*`. The target file remains completely untouched.
2. **Crash during Rename**: On Linux/POSIX, `rename(2)` / `os.replace` is atomic; either the old file or new file is visible, never a corrupted mixture.
3. **Stale Temp File Cleanup**: On startup, `tacp doctor` sweeps and unlinks orphaned `.tacp_tmp_*` files older than 1 hour.
