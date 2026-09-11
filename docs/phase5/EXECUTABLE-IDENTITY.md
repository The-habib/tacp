# TACP Phase 5: Executable Identity Specification
**Document ID:** `TACP-EXE-IDENT-001`  
**Classification:** Execution Subsystem Architecture  
**Release Target:** v0.4.0-rc.1 Hardening / Phase 5  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Threat Definition & Motivation

In previous iterations, binary resolution answered the question:
> *"Which path on the filesystem currently has this filename?"*

This permitted critical security vulnerabilities:
1. **Executable Path Substitution:** If a caller provided `./printf`, `/tmp/printf`, or `<workspace>/bin/printf`, the previous resolver checked whether the file was named `printf` and was executable, but never verified that the binary resided inside a trusted operating system root.
2. **Symlink Confusion:** A symlink named `printf` could point to an untrusted location or an unpermitted utility.
3. **Multicall Inconsistencies:** In Android and Termux, system utilities are frequently symlinks to multicall binaries (such as `coreutils` in Termux and `toybox` in Android `/system/bin`). Resolving solely to the realpath target without multicall-aware identity policies breaks either execution semantics or security filtering.

---

## 2. Hardened Executable Identity Model

Under Phase 5, `ExecutionResolver` implements a 7-stage identity verification pipeline:

```
Caller Input ("printf" or "/system/bin/printf")
   │
   ▼
[1] Input & Path Sanitization (No null bytes, no "..")
   │
   ▼
[2] Basename Whitelist Check (Must be in {"printf", "echo", "true"})
   │
   ▼
[3] Trusted Root Containment Check (Candidate must reside in SAFE_SEARCH_PATHS)
   │
   ▼
[4] Realpath Resolution (Symlinks traversed to underlying binary)
   │
   ▼
[5] Target Trusted Root Check (Target realpath must ALSO reside in SAFE_SEARCH_PATHS)
   │
   ▼
[6] Multicall & Target Policy (Target must be in Whitelist OR TRUSTED_MULTICALL_BINARIES)
   │
   ▼
[7] Filesystem Permission & Digest Verification (Non-world-writable, Inode + SHA-256)
   │
   ▼
Deterministic ExecutableIdentity Object
```

### 2.1 Trusted Search Roots
Executable candidates and their real targets must reside strictly within:
1. `/data/data/com.termux/files/usr/bin` (Termux system package root)
2. `/system/bin` (Android immutable system partition)
3. `/usr/bin` (Standard POSIX host root)
4. `/bin` (Standard POSIX core root)

Any executable outside these roots (e.g. in `/data/local/tmp`, `/sdcard`, or workspace directories) is rejected with `TacpSecurityError(ErrorCode.NOT_AUTHORIZED)`.

### 2.2 Multicall Binary Policy
On Android/Termux:
- `/data/data/com.termux/files/usr/bin/printf` -> `coreutils`
- `/system/bin/printf` -> `toybox`

The policy mandates:
- The entry point basename must be in `PERMITTED_EXECUTABLE_NAMES` (`{"printf", "echo", "true"}`).
- The underlying target binary must be in `PERMITTED_EXECUTABLE_NAMES | TRUSTED_MULTICALL_BINARIES` (`{"coreutils", "toybox", "toolbox", "busybox"}`).
- Target binaries must not be in `FORBIDDEN_EXECUTABLE_NAMES` (e.g. `bash`, `sh`, `python`).

### 2.3 Cryptographic Executable Identity Structure
Every resolved binary produces an immutable `ExecutableIdentity` record:
- `canonical_path`: Absolute path to the trusted entry point.
- `basename`: Standard entry name.
- `trusted_root`: Canonical path of the matching trusted directory.
- `inode`: Filesystem inode number.
- `device`: Filesystem device ID.
- `size`: Binary file size in bytes.
- `sha256_digest`: SHA-256 cryptographic checksum of the binary content, cached by `(inode, device, mtime_ns)`.
