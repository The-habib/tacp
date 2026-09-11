# TACP Slice 1 Negative API & Architectural Boundary Audit

**Target:** TACP v0.2.0-rc.1 (`src/tacp/`)  
**Commit:** `bd827d8`  
**Date:** September 11, 2026  
**Auditor:** Independent Systems & Security Auditor  
**Audit Scope:** Verification of ungoverned mutation, execution, and networking primitives in production source tree.

---

## 1. Executive Summary

An exhaustive scan across all 40 Python source files in `src/tacp/` was performed to identify any ungoverned execution or mutation primitives.

### Primary Audit Findings:
1. **Zero Execution Bypasses**: There are **0 occurrences** of `subprocess`, `Popen`, `os.system`, `os.popen`, or `shell=True` in the entire `src/tacp/` tree.
2. **Zero Network Egress Bypasses**: There are **0 occurrences** of `socket`, `requests`, `urllib`, or `http` client libraries in `src/tacp/`.
3. **Zero Arbitrary Filesystem Mutation**: There are **0 occurrences** of uncontrolled file creation, deletion, or permission changes (`chmod`, `chown`, `os.remove`).
4. **Governed Mutation Invariants**: Exactly 16 occurrences of negative pattern matches were identified; every single occurrence belongs to either JSON-RPC stdio protocol communication, CLI error reporting, or strictly bounded, governed patch staging/replacement in `FilesystemProvider`.

---

## 2. Exhaustive Primitive Inventory in `src/tacp/`

| Location | Line | Primitive Type | Code Snippet | Classification | Architecture Role | Security Assessment |
| :--- | :---: | :--- | :--- | :--- | :--- | :--- |
| `src/tacp/access/mcp/server.py` | 213 | `write_ops` | `out_stream.write(response.to_json() + "\n")` | Production / Expected | Transport Layer (Stdio) | **SAFE**: MCP JSON-RPC protocol response stream |
| `src/tacp/access/mcp/server.py` | 217 | `write_ops` | `out_stream.write(err_resp.to_json() + "\n")` | Production / Expected | Transport Layer (Stdio) | **SAFE**: MCP JSON-RPC error response stream |
| `src/tacp/access/mcp/server.py` | 224 | `write_ops` | `out_stream.write(err_resp.to_json() + "\n")` | Production / Expected | Transport Layer (Stdio) | **SAFE**: MCP JSON-RPC error response stream |
| `src/tacp/cli/main.py` | 160 | `write_ops` | `sys.stderr.write(f"Notice: Workspace not registered: ...")` | Production / Expected | CLI User Interface | **SAFE**: Standard error reporting to user console |
| `src/tacp/control/policy.py` | 153 | `run` (lexical) | `reason="Authorized dry-run evaluation..."` | Production / String literal | Policy Engine | **SAFE**: Log/audit reason text containing substring 'run' |
| `src/tacp/control/risk.py` | 7 | `run` (lexical) | `R1 = "R1"  # Low-impact mutation / dry-run` | Production / Comment | Risk Rating | **SAFE**: Comment text containing substring 'run' |
| `src/tacp/providers/filesystem.py` | 498 | `run` (lexical) | `"message": "Dry-run patch simulation succeeded"` | Production / String literal | Provider Result | **SAFE**: Message string containing substring 'run' |
| `src/tacp/providers/filesystem.py` | 506 | `write_ops` | `snap_file.write_bytes(file_bytes)` | Production / Expected | Snapshot Storage | **SAFE & GOVERNED**: Creates pre-mutation snapshot in `~/.tacp/snapshots/{patch_id}/` |
| `src/tacp/providers/filesystem.py` | 519 | `open_write` | `with temp_file.open("wb") as f:` | Production / Expected | Atomic Staging | **SAFE & GOVERNED**: Writes staged diff to `.tacp_tmp_{uuid}` in same directory |
| `src/tacp/providers/filesystem.py` | 520 | `write_ops` | `f.write(resulting_bytes)` | Production / Expected | Atomic Staging | **SAFE & GOVERNED**: Buffers patched bytes to temporary file |
| `src/tacp/providers/filesystem.py` | 523 | `replace` | `os.replace(temp_file, target)` | Production / Expected | Atomic Commit | **SAFE & GOVERNED**: Atomic replacement of target file via POSIX inode rename |
| `src/tacp/providers/filesystem.py` | 526 | `unlink` | `temp_file.unlink(missing_ok=True)` | Production / Expected | Failure Recovery | **SAFE & GOVERNED**: Cleans up temporary staging file if write or replace fails |
| `src/tacp/providers/filesystem.py` | 586 | `open_write` | `with temp_file.open("wb") as f:` | Production / Expected | Rollback Staging | **SAFE & GOVERNED**: Writes snapshot bytes to `.tacp_tmp_{uuid}` for rollback |
| `src/tacp/providers/filesystem.py` | 587 | `write_ops` | `f.write(snap_bytes)` | Production / Expected | Rollback Staging | **SAFE & GOVERNED**: Buffers rollback snapshot bytes |
| `src/tacp/providers/filesystem.py` | 590 | `replace` | `os.replace(temp_file, target)` | Production / Expected | Rollback Commit | **SAFE & GOVERNED**: Atomic restoration of original snapshot |
| `src/tacp/providers/filesystem.py` | 593 | `unlink` | `temp_file.unlink(missing_ok=True)` | Production / Expected | Failure Recovery | **SAFE & GOVERNED**: Cleans up rollback staging file if restore fails |

---

## 3. Absence of Ungoverned Execution Vectors

The following critical system primitives were scanned for and confirmed to have **zero occurrences** in `src/tacp/`:
- `subprocess.run`, `subprocess.Popen`, `subprocess.call`, `subprocess.check_output`: **0**
- `os.system`, `os.popen`, `os.spawn*`, `os.exec*`: **0**
- `pty`, `fcntl` ioctls for terminal spawning: **0**
- `socket.socket`, `socket.create_connection`: **0**
- `urllib.request`, `http.client`, `requests`, `httpx`, `aiohttp`: **0**
- `os.chmod`, `os.chown`, `os.setuid`, `os.setgid`: **0**
- `shutil.rmtree` or `os.remove` targeting arbitrary workspace paths: **0**

---

## 4. Architectural Boundary Verdict

**Boundary Status:** **ENFORCED & SOUND**  
No backdoor, bypass, or ungoverned execution path exists from MCP or CLI into the underlying operating system. Mutation is strictly quarantined to `FilesystemProvider.apply_patch` and `FilesystemProvider.rollback_patch`.
