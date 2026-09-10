# TACP Environment Discovery & Audit Report

**Timestamp**: 2026-09-10T21:14:00Z  
**Host**: localhost (Termux on Android)  
**Assessor**: Antigravity Lead Staff Engineer / DevOps / Security Lead  
**Status**: AUDIT COMPLETE — READY FOR BOOTSTRAP  

---

## 1. Executive Summary

This document establishes the verified baseline of the operating environment for the **TACP (Termux AI Control Plane)** project. All findings are derived from direct, read-only system inspection inside Termux on an Android device.

No assumptions have been made. Every external tool is classified according to its verified availability.

---

## 2. Android & Device Environment

| Attribute | Detected Value | Classification |
|---|---|---|
| **OS** | Android 16 (API Level 36) | AVAILABLE |
| **Linux Kernel** | `5.15.197-android13-8-00049-g7d37760ec777-ab15613975` (aarch64) | AVAILABLE |
| **CPU Architecture** | `aarch64` (`arm64-v8a`) | AVAILABLE |
| **Hardware Manufacturer** | Vivo | AVAILABLE |
| **Device Model** | `V2348` | AVAILABLE |
| **System Memory (RAM)** | Total: 7.1 GiB / Available: 1.9 GiB / Swap: 8.0 GiB (3.9 GiB used) | AVAILABLE |
| **Storage (`/data`)** | Total: 103 GiB / Used: 94 GiB / Available: 8.5 GiB (92% capacity) | AVAILABLE (CONSTRAINED) |
| **SELinux Process Context** | `u:r:untrusted_app_27:s0:c60,c257,c512,c768` | AVAILABLE (ENFORCING) |
| **SELinux File Context** | `u:object_r:app_data_file:s0:c60,c257,c512,c768` | AVAILABLE (ENFORCING) |
| **Battery / Power State** | Direct `/sys/class/power_supply` restricted by Android sandbox | RESTRICTED |
| **Direct Bridge (`adb`)** | Not installed in PATH | MISSING (OPTIONAL) |
| **Root Privileges (`su`)** | Binary present at `/data/data/com.termux/files/usr/bin/su`, but unprivileged non-root execution used for TACP | PRESENT (UNUSED) |

---

## 3. Termux Environment

| Attribute | Detected Value | Classification |
|---|---|---|
| **Termux Version** | `0.118.3` (Release: `F_DROID`) | AVAILABLE |
| **Package Manager** | `apt` / `pkg` (Debian format) | AVAILABLE |
| **targetSdkVersion** | 28 (permits standard W^X and exec behavior) | AVAILABLE |
| **PREFIX** | `/data/data/com.termux/files/usr` | AVAILABLE |
| **HOME** | `/data/data/com.termux/files/home` | AVAILABLE |
| **Shell** | `/data/data/com.termux/files/usr/bin/bash` | AVAILABLE |
| **Termux Tools Version** | `1.45.0` | AVAILABLE |
| **Subscribed Repositories** | `mirror.sunred.org/termux/termux-main` (stable main)<br>`packages-cf.termux.dev/apt/termux-glibc` (glibc stable) | AVAILABLE |
| **Termux:API Package** | Not installed initially (available via `pkg install termux-api`) | OPTIONAL |
| **Termux:Boot** | Not installed | OPTIONAL |
| **PRoot** | Not installed | OPTIONAL |

---

## 4. Programming Toolchain & Utilities

| Tool / Utility | Version | Installation Source | Classification |
|---|---|---|---|
| **Python** | `3.14.6` | Termux Native (`pkg`) | AVAILABLE |
| **pip** | `26.2.1` | Termux Native (`pkg`) | AVAILABLE |
| **uv** | `0.12.12` | Termux Native (`pkg`) | AVAILABLE |
| **Node.js** | `v26.4.0` | Termux Native (`pkg`) | AVAILABLE |
| **npm** | `11.19.1` | Termux Native (`pkg`) | AVAILABLE |
| **npx** | `11.19.1` | Termux Native (`pkg`) | AVAILABLE |
| **Git** | `2.55.0` | Termux Native (`pkg`) | AVAILABLE |
| **GitHub CLI (`gh`)** | `2.100.0` | Termux Native (`pkg`) | AVAILABLE |
| **Clang** | `21.1.8` | Termux Native (`pkg`) | AVAILABLE |
| **Rustc** | `1.98.1` | Termux Native (`pkg`) | AVAILABLE |
| **Make** | `GNU Make 4.4.1` | Termux Native (`pkg`) | AVAILABLE |
| **jq** | `1.8.2` | Termux Native (`pkg`) | AVAILABLE |
| **ripgrep (`rg`)** | `15.2.0` (with PCRE2 & NEON) | Termux Native (`pkg`) | AVAILABLE |
| **ShellCheck** | `0.11.0` | Termux Native (`pkg`) | AVAILABLE |
| **curl** | System cURL | Termux Native (`pkg`) | AVAILABLE |
| **sed / awk / tar / unzip** | Coreutils / standard | Termux Native (`pkg`) | AVAILABLE |
| **OpenSSL CLI** | Available via `openssl-tool` (1:3.6.3) | Termux Native (`pkg`) | AVAILABLE (AS NEEDED) |
| **rsync** | Available via `rsync` (3.5.0-1) | Termux Native (`pkg`) | AVAILABLE (AS NEEDED) |
| **tmux** | Available via `tmux` (3.7c) | Termux Native (`pkg`) | AVAILABLE (AS NEEDED) |

---

## 5. Antigravity & AI Agent Environment

| Attribute | Detected Value | Classification |
|---|---|---|
| **CLI Binary** | `/data/data/com.termux/files/usr/bin/agy` | AVAILABLE |
| **Version** | `1.1.16` | AVAILABLE |
| **Active Model** | `gemini-3.8-flash-high` | AVAILABLE |
| **Config Directory** | `/data/data/com.termux/files/home/.gemini/antigravity-cli` | AVAILABLE |
| **Global Agent Directory** | `/data/data/com.termux/files/home/.agents/skills` (87 skills) | AVAILABLE |
| **Global Rules** | None (`~/.agents/rules` was not present) | PROJECT-SCOPED RULESPACE AVAILABLE |
| **Configured MCP Servers** | None (`agy mcp list` reported empty) | READY FOR DEVELOPMENT |
| **Imported Plugins** | None (`agy plugin list` reported empty) | CLEAN |

---

## 6. Git & GitHub Configuration

| Attribute | Detected Value | Classification |
|---|---|---|
| **Git User Name** | `the-habib` | CONFIGURED |
| **Git User Email** | `tgff28970@email.com` | CONFIGURED |
| **Credential Helper** | `gh auth git-credential` (linked to GitHub CLI) | CONFIGURED |
| **GitHub User Account** | `The-habib` | AUTHENTICATED |
| **GitHub Plan / Type** | `User` (Personal Account) | ACTIVE |
| **Token Scopes** | `gist`, `read:org`, `repo`, `workflow` | SUFFICIENT FOR CI & REPO CREATION |
| **Git Protocol** | HTTPS | SECURE |
| **Target Repository** | `The-habib/tacp` (Not yet created on GitHub) | PLANNED (PRIVATE) |

---

## 7. Security & Environment Observations

1. **Storage Utilization**: Storage partition `/data` is at 92% usage (8.5 GiB available). Caches, temporary directories, and verification runs must avoid unbound disk accumulation.
2. **No Root Requirement**: TACP operates strictly inside the standard Termux unprivileged application domain (`untrusted_app_27`). No root access or privileged elevation will be permitted or required.
3. **Zero Secrets in Environment**: Initial audit of environment variable names and shell history found no leaked access keys, passwords, or plain-text secrets. Token values are handled exclusively via `gh auth git-credential` without persisting plaintext tokens into repository files.
4. **Clean Workspace Isolation**: The project directory `/data/data/com.termux/files/home/projects/tacp` is completely isolated from other projects on the device.

---

## 8. Classification Legend

- **AVAILABLE**: Verified installed, operational, and tested.
- **MISSING**: Not present, required for certain optional tasks.
- **OPTIONAL**: Can be installed on demand when explicitly justified.
- **UNSUPPORTED**: Incompatible with current platform constraints.
- **UNKNOWN**: Status not verifiable with current evidence.
- **EXPERIMENTAL**: Unproven stability in this specific environment.
