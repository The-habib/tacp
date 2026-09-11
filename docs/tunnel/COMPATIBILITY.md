# Official Compatibility & Environment Report

## 1. Physical Device & Operating Environment
* **Platform**: Android 13 (API Level 33)
* **Architecture**: `aarch64` (ARM 64-bit Little-Endian)
* **Kernel**: Linux 4.19.157-perf+
* **Environment**: Termux native userspace (`/data/data/com.termux/files/usr`)
* **Python Runtime**: Python 3.14.6 in virtual environment (`.venv`)
* **Node.js**: v26.4.0 / npm 11.19.1

## 2. OpenAI Tunnel Client Compatibility
* **Upstream Repository**: `https://github.com/openai/tunnel-client`
* **Release Verified**: `v0.0.14`
* **Artifact**: `tunnel-client-v0.0.14-linux-arm64.zip`
* **Binary Path**: `/data/data/com.termux/files/usr/bin/tunnel-client`
* **Verified SHA-256**: `2de3fb879a18edb847e0313592c912f1983685488290a7fdba7ac403e6a4fb0a`
* **Compilation Details**: Statically linked Go binary (no glibc, musl, or dynamic linker dependencies required).
* **Execution Verification**:
  ```bash
  $ tunnel-client --version
  tunnel-client version 0.0.14+0f870e50a973fa820d4c409000059e181e8d242b
  ```
* **Verdict**: **100% NATIVE COMPATIBILITY**. No proot, chroot, containerization, or kernel modification is required.

## 3. Protocol & Client Compatibility
* **Protocol Standard**: Model Context Protocol (MCP) JSON-RPC 2.0
* **Supported Versions**:
  * `2026-07-28` (Primary)
  * `2024-11-05` (Backward Compatibility)
* **Target AI Client**: ChatGPT (OpenAI Custom MCP Connector via Secure Tunnel)
* **Transport**: Local `stdio` pipe between `tunnel-client` and `tacp serve`
* **Compatibility Status**: **READY FOR READ-ONLY OBSERVATION**.
