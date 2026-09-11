# TACP Phase 5: Cross-Platform & Environment Compatibility Matrix
**Document ID:** `TACP-COMPAT-001`  
**Classification:** Conformance & Support Specification  
**Release Target:** v0.4.0-rc.1 Hardening / Phase 5  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Scope & Purpose

This document specifies the validated execution targets, operating system environments, Python runtimes, CPU architectures, and multicall binary implementations supported by the TACP execution core.

---

## 2. Operating System & Platform Support

| Operating System / Platform | Support Tier | Validation Status | Notes & Constraints |
|---|---|---|---|
| **Android 13 / Termux (aarch64)** | **Tier 1 (Primary)** | **Fully Validated on Hardware** | Physical reference device; Bionic libc; coreutils & toybox |
| **Android 11, 12, 14 / Termux** | Tier 1 (Primary) | Validated via API contracts | Requires F-Droid / GitHub build of Termux (API >= 29) |
| **Android 10 / Termux (Legacy)** | Tier 2 (Supported) | Conformance Verified | Deprecated W^X behavior; compatible with standard paths |
| **Ubuntu 22.04 / 24.04 LTS (x86_64)** | Tier 1 (CI/Dev) | Validated in CI Pipeline | Uses `/usr/bin`, glibc, standard GNU coreutils |
| **Debian 12 Bookworm (x86_64 / arm64)** | Tier 1 (CI/Dev) | Validated in Container CI | Standard search paths; glibc |
| **Alpine Linux 3.19+ (x86_64 / aarch64)** | Tier 2 (Supported) | Validated (Busybox target) | Musl libc; `/bin/busybox` multicall binary support |
| **macOS 13+ (Darwin ARM64 / x86_64)** | Tier 3 (Experimental) | Developer Workstation | `setsid` / `killpg` functional; paths adapt to `/usr/bin` |
| **Google Play Termux (Legacy)** | **UNSUPPORTED** | **BLOCKED** | Deprecated builds (abandoned since 2020); cannot run modern Python |

---

## 3. Python Runtime Compatibility

| Python Version | Status | CI Verification | Notes |
|---|---|---|---|
| **Python 3.14** | **Primary (On-Device)** | **Passing (689/689)** | Default Python package on modern Termux aarch64 |
| **Python 3.13** | Supported | Verified Clean | Fully conforms to strict typing and exception hierarchies |
| **Python 3.12** | Supported | Verified Clean | Standard LTS Linux distribution default |
| **Python 3.11** | Minimum Supported | Verified Clean | Baseline minimum per `pyproject.toml` (`requires-python = ">=3.11"`) |
| **Python <= 3.10** | **Unsupported** | Rejected at packaging | Lacks required type union and dataclass enhancements |

---

## 4. Hardware Architectures

| Architecture | Word Size | Endianness | Support Level |
|---|---|---|---|
| **`aarch64` (ARM64)** | 64-bit | Little Endian | Primary Production Target (Physical Android Devices) |
| **`x86_64` (AMD64)** | 64-bit | Little Endian | Primary Development / CI Target |
| **`armv7l` (32-bit ARM)** | 32-bit | Little Endian | Supported (subject to 32-bit `max_stdout_bytes` constraints) |
| **`x86` (32-bit i686)** | 32-bit | Little Endian | Legacy / CI only |

---

## 5. Multicall Binary Implementation Differences

The initial Phase 4 & Phase 5 capability allowlist permits exactly three utilities: `printf`, `echo`, and `true`.

The following matrix documents behavioral equivalence across multicall implementations:

| Binary | GNU Coreutils | Toybox (Android System) | Busybox (Alpine/Embedded) | Toolbox (Legacy Android) | TACP Normalized Contract |
|---|---|---|---|---|---|
| `printf` | Full POSIX + GNU format specifiers | POSIX standard format specifiers | POSIX standard format specifiers | Minimal format specifiers | Strictly constrained format string + arguments |
| `echo` | Supports `-n`, `-e`, `-E` | Supports `-n`, `-e` | Supports `-n`, `-e` | Unpredictable flag handling | Arguments only; flag bypasses prohibited |
| `true` | Exits 0, ignores arguments | Exits 0, ignores arguments | Exits 0, ignores arguments | Exits 0 | Deterministic exit code 0 |

### Critical Safety Invariant:
Because `echo` exhibits implementation variations across Toybox, Coreutils, and Builtins regarding flag interpretation (e.g. `-e`, `-n`, `-E`), `printf` is designated the **canonical standard output command** for high-reliability agent tasks.

---

## 6. Dependency Footprint: Zero Runtime Dependencies

TACP achieves maximum cross-platform compatibility by having **zero runtime third-party dependencies**:
- SQLite 3: Standard library (`sqlite3`)
- Cryptography: Standard library (`hashlib.sha256`)
- Process Management: Standard library (`subprocess.Popen`, `os`, `signal`)
- JSON / RPC: Standard library (`json`)
- Date / Time: Standard library (`datetime.timezone.utc`)

This guarantees zero supply-chain drift and instant portability across all supported environments.
