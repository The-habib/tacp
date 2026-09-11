# Phase 2 — Vertical Slice 1: Device & Android Mechanics Report

**Execution Environment:** Termux on Android  
**Architecture:** Linux Kernel / aarch64 / Bionic libc  
**Primary Storage Path:** `/data/data/com.termux/files/home`

---

## 1. Android Filesystem Mechanics & Mitigations

Operating on an Android host presents unique filesystem behaviors and constraints not present on standard desktop Linux distributions:

### 1.1 Mitigation of Cross-Device `EXDEV` Errors
- **The Problem**: Standard Linux utilities often create temporary files in `/tmp` or system temp directories. On Android, `/data/data/com.termux/files` resides on an `ext4` or `f2fs` private volume, while shared storage (`/sdcard`) resides on an emulated FUSE mount. Attempting to `os.rename()` or `os.replace()` between distinct mount points triggers an `EXDEV (Invalid cross-device link)` error.
- **TACP Solution**: TACP's `FilesystemProvider` mandates that all temporary files (`.tacp_tmp_{uuid}`) are created in the **exact same parent directory** as the target file:
  ```python
  temp_file = target.parent / f".tacp_tmp_{uuid.uuid4().hex}"
  ```
  This guarantees that `os.replace` operates strictly within the same filesystem mount and directory inode table, making atomic replacement 100% reliable across any mount.

### 1.2 Durability Against Android OOM (LowMemoryKiller)
- **The Problem**: Android's memory management subsystem aggressively terminates background applications (LowMemoryKiller). If an app is killed while file buffers are uncommitted, data loss or truncation occurs.
- **TACP Solution**: Every atomic write in TACP performs explicit flushing and synchronization to physical storage before replacing the target:
  ```python
  with temp_file.open("wb") as f:
      f.write(resulting_bytes)
      f.flush()
      os.fsync(f.fileno())
  os.replace(temp_file, target)
  ```

### 1.3 SQLite Concurrency via WAL Mode
- SQLite is configured with `PRAGMA journal_mode=WAL;` and `PRAGMA synchronous=NORMAL;`.
- This ensures that concurrent reads (e.g. audit inspections or policy evaluations) do not block or get blocked by active patch transactions or lock acquisitions.
