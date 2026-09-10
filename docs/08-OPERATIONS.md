# TACP Operational Procedures

**Status**: PROPOSED BASELINE  
**Target Phase**: Phase 0-6  

---

## 1. Operating Environment Characteristics

- **Host**: Termux on Android 16 (Vivo V2348, aarch64).
- **Execution Mode**: Non-root, unprivileged Android user domain.
- **Resource Constraints**: 1.9 GiB available RAM, 8.5 GiB available storage.

---

## 2. Process & Lifecycle Management

- **Background Execution**: Android OS aggressively kills background processes. Long-running TACP tasks must acquire Termux wake locks (`termux-wake-lock`) when running active jobs, and release them promptly.
- **Crash Recovery**: TACP processes must implement idempotent startup. If Termux is terminated, restarting the control plane must recover state cleanly from the local SQLite/WAL store.

---

## 3. Health Checks & Diagnostics

- **Canonical Doctor**: `./doctor` evaluates system prerequisites, environment variables, git status, and dependencies.
