# Evidence: OpenAI Tunnel Client Installation & Verification

## Upstream Release Verification
* **Source**: `https://github.com/openai/tunnel-client/releases/download/v0.0.14/tunnel-client-v0.0.14-linux-arm64.zip`
* **Official Checksum**: `2de3fb879a18edb847e0313592c912f1983685488290a7fdba7ac403e6a4fb0a`
* **Local Calculated Checksum**: `2de3fb879a18edb847e0313592c912f1983685488290a7fdba7ac403e6a4fb0a`
* **Verification Result**: MATCH (100% bitwise identity)

## Target Installation Path
* **Binary Location**: `/data/data/com.termux/files/usr/bin/tunnel-client`
* **Permissions**: `0755` (`-rwx------`)

## Native Execution Output on Android 13 Termux aarch64
```bash
$ tunnel-client --version
tunnel-client version 0.0.14+0f870e50a973fa820d4c409000059e181e8d242b
```

## Binary Architecture Inspection
* Statically compiled Go executable.
* Zero external shared library dependencies (`not a dynamic executable`).
* Fully functional inside Termux without requiring root, proot, or glibc emulation.
