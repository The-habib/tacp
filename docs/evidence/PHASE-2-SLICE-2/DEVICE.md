# Phase 2 — Vertical Slice 2: Android Termux Device Mechanics

- **Environment:** Termux on Linux 5.15.197 Android 13 aarch64
- **Filesystem Constraints & Mitigations:**
  1. **Cross-Device Link Avoidance (`EXDEV`):**
     Temporary files for staging are created in each target file's parent directory (`.tacp_tmp_{batch_id}_{idx}_{uuid}`), guaranteeing same-filesystem atomicity for `os.replace`.
  2. **Durable Persistence (`fsync`):**
     Every staged file and snapshot file is flushed and synced using `os.fsync(f.fileno())` before rename or commit.
  3. **Lexicographical Resource Locking:**
     Batch locks are acquired in strictly sorted lexicographical order (`f"{workspace_id}:{subpath}"`), preventing deadlocks on concurrent multi-agent executions.
  4. **Emergency Rollback on Crash/Failure:**
     Pre-mutation snapshots are archived with individual file permissions preserved and verified before any staging begins.
