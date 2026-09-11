# TACP Phase 5: Android / Termux Device Security & Hardware Validation Report
**Document ID:** `TACP-DEV-SEC-001`  
**Classification:** Device Validation & Hardware Audit  
**Target Environment:** Android 13 / Termux `aarch64`  
**Host Context:** Samsung / Android Linux Kernel 5.10.x, Bionic libc  
**Date:** September 2026  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Executive Summary

Controlled operating-system process execution cannot be audited in abstract desktop or containerized mock environments. Android enforces a security model fundamentally different from conventional GNU/Linux:
1. Every application executes as an isolated Linux UID (`u0_a316`) governed by SELinux domains.
2. The C standard library is Bionic, not glibc or musl.
3. System utilities (`/system/bin`) are multicall symlinks to `toybox` or `toolbox`.
4. Termux userland utilities (`/data/data/com.termux/files/usr/bin`) are multicall symlinks to GNU `coreutils` or standalone ELF binaries.
5. Standard Linux filesystem hierarchies (`/bin`, `/usr/bin`, `/etc`, `/tmp`) either do not exist or are restricted read-only root mounts.

This report documents empirical hardware-level security validation of TACP Phase 5 on a physical Android `aarch64` device.

---

## 2. Host Environment & Hardware Profile

| Metric | Target Specification | Observed Device Value | Security Consequence |
|---|---|---|---|
| **Architecture** | `aarch64` (ARM64) | `aarch64` | 64-bit pointer integrity, ARMv8 memory model |
| **Operating System** | Android 13 | Android 13 (API Level 33) | Modern Bionic linker, W^X enforcement |
| **Linux Kernel** | Linux 5.x | Linux 5.10.136-android12-9-26884872 | Modern seccomp, namespaces, `/proc` isolation |
| **UID / GID** | Unprivileged App UID | `u0_a316` (UID 10316) | Zero root access; sandboxed from other apps |
| **SELinux Context** | Untrusted App Domain | `u:r:untrusted_app_29:s0:c316,c768` | Kernel denies raw sockets, ptrace, and kmod loading |
| **Process Root** | Termux Home Prefix | `/data/data/com.termux/files/home` | Confined app-private storage; inaccessible to other UIDs |
| **Python Runtime** | CPython 3.14.6 (Termux) | 3.14.6 aarch64 (Bionic libc) | Standard library zero external C-extension dependencies |

---

## 3. Physical Filesystem & Symlink Topology

### 3.1 Safe Search Roots
TACP defines `SAFE_SEARCH_PATHS` ordered by trust priority:
1. `/data/data/com.termux/files/usr/bin` (Termux userland binaries)
2. `/system/bin` (Android system binaries)
3. `/usr/bin` (Fallback on standard Linux host)
4. `/bin` (Fallback on standard Linux host)

### 3.2 Multicall Binary Verification on Device
Investigation of physical symlink targets revealed:
- `/data/data/com.termux/files/usr/bin/printf` is a symlink to `/data/data/com.termux/files/usr/bin/coreutils`.
- `/system/bin/printf` is a symlink to `/system/bin/toybox`.
- `/system/bin/echo` is a symlink to `/system/bin/toybox` (or toolbox on older Androids).

**TACP Enforcement:**
TACP's `ExecutionResolver` requires that:
1. The candidate path MUST reside inside an existing trusted search path.
2. The real target (`Path.resolve()`) MUST also reside strictly inside an existing trusted search path.
3. The real target's basename MUST belong to `PERMITTED_EXECUTABLE_NAMES` OR `TRUSTED_MULTICALL_BINARIES` (`{"coreutils", "toybox", "toolbox", "busybox"}`).
4. Target binaries MUST NOT be world-writable (`st_mode & 0o002 == 0`).

---

## 4. Process Isolation & Containment on Android

### 4.1 Process Groups & Session Leader (`setsid`)
On Android, child processes spawned by background threads must not leak or outlive the control plane.
- TACP enforces `preexec_fn=os.setsid` in `subprocess.Popen`.
- This creates an independent process group (`pgid = pid`).
- Signal delivery for termination (`SIGTERM`) and hard killing (`SIGKILL`) is dispatched to `-pgid` via `os.killpg(pgid, sig)`.
- Physical device testing verified that killing the process group cleans up any spawned child processes without leaving zombies in the process table.

### 4.2 File Descriptor Leakage Defense
- Bionic libc implements standard POSIX file descriptors.
- TACP explicitly passes `close_fds=True` in `subprocess.Popen`.
- Open SQLite database handles, audit log file descriptors, and terminal sockets are guaranteed closed in the child process.

### 4.3 Output Stream Model B Defense
- On mobile devices, memory exhaustion (OOM) triggers the Android Low Memory Killer (LMK), which unconditionally terminates background processes.
- TACP Model B terminates the process group immediately upon exceeding `max_stdout_bytes` (default 64KB, configurable).
- Subprocess output buffers are capped with strict byte accounting, preventing out-of-memory kernel kills of the control plane.

---

## 5. Network Non-Isolation Truth on Android

TACP explicitly rejects false security theater:
- On unrooted Android/Termux, network isolation via Linux network namespaces (`CLONE_NEWNET`) requires `CAP_SYS_ADMIN`, which is unavailable to unprivileged Android apps (`u0_a316`).
- TACP records `NetworkIsolationState.NETWORK_UNENFORCED` or `NETWORK_DENIED` in the cryptographically hashed execution contract.
- TACP strips network proxy environment variables (`HTTP_PROXY`, `HTTPS_PROXY`, etc.) to prevent inadvertent proxy escapes.

---

## 6. Device Audit Conclusion

The execution subsystem has been verified against the physical reality of Android 13 / Termux `aarch64`. All security assumptions are grounded in real filesystem paths, Bionic libc behaviors, and Android Linux kernel constraints.
