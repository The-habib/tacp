# TACP Real-Device Validation Plan

**Status**: ACTIVE BASELINE  

---

## 1. Fundamental Principle

> **"CI CANNOT PROVE ANDROID-SPECIFIC BEHAVIOR."**

GitHub Actions runs inside standard x86_64 Ubuntu virtual machines. While CI validates pure Python logic, typing, formatting, and abstract algorithms, it cannot prove compatibility with:
- Android Bionic libc peculiarities
- Android SELinux domain sandboxing (`untrusted_app_27`)
- `/data/data/com.termux/files/usr` prefix conventions
- Android battery-saver and Doze mode process termination
- ARM64 (`aarch64`) memory and instruction set behavior

---

## 2. Validation Matrix

| Environment | Purpose | Authority on Android Reality |
|---|---|---|
| **GitHub Actions** | Lint, typecheck, unit logic, PR gating | Simulation / Fast Feedback |
| **Local Termux** | Native tool execution, on-device testing | **Authoritative Reality** |
