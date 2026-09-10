# TACP Compatibility Matrix

**Last Verified**: 2026-09-10  

---

| Dependency / Component | Current Detected | Target Version | Compatibility Status | Verification Method | Notes |
|---|---|---|---|---|---|
| **Android OS** | Android 16 (API 36) | Android 12+ (API 31+) | COMPATIBLE | Direct System Query | Tested on Vivo V2348 |
| **Kernel** | 5.15.197 (aarch64) | 4.19+ | COMPATIBLE | `uname -a` | 64-bit ARM architecture |
| **Termux** | 0.118.3 | 0.118.0+ | COMPATIBLE | `termux-info` | F-Droid release build |
| **Python** | 3.14.6 | 3.11 - 3.14 | COMPATIBLE | `python3 --version` | Termux native package |
| **uv** | 0.12.12 | 0.10+ | COMPATIBLE | `uv --version` | Fast installer / resolver |
| **Node.js** | v26.4.0 | 20+ | COMPATIBLE | `node --version` | Termux native package |
| **Git** | 2.55.0 | 2.40+ | COMPATIBLE | `git --version` | Termux native package |
| **GitHub CLI (gh)** | 2.100.0 | 2.60+ | COMPATIBLE | `gh --version` | Fully authenticated |
| **MCP Python SDK** | 2.2.0 | 2.0+ | PLANNED | PyPI Package Check | Will be pulled via `uv` |
| **Antigravity CLI** | 1.1.16 | 1.1+ | COMPATIBLE | `agy --version` | Main agent interface |
