# FINAL TACP ANDROID DEVICE CONTROL PLANE REPORT

**Device:** vivo V2348 (`crow`) | **OS:** Android 16 (SDK 36) | **Kernel:** Linux aarch64
**Generated:** 2026-09-24T20:26:16.091295+00:00 | **Total Capabilities:** 68
**Verification:** 785/785 Tests Passed (100% Pass Rate in 57.46s)

---

## 1. Executive Summary

TACP (Termux AI Control Plane) has been completely elevated from a workspace file-patching server into an **advanced, capability-oriented Android Device Control MCP Server**.

### Key Architectural Pillars
1. **Dynamic Multi-Backend Resolution Engine**: Seamless execution across 7 backends (`termux`, `android_shell`, `termux_api`, `shizuku`, `root`, `adb`, `android_bridge`).
2. **Zero Fake Success Policy**: If a capability lacks the required companion or privilege, TACP returns explicit, structured requirements (`SHIZUKU_REQUIRED`, `ROOT_REQUIRED`, `COMPANION_REQUIRED`, `PERMISSION_REQUIRED`) with actionable instructions rather than faking execution.
3. **Complete MCP Subsystem Exposure**: 80+ MCP tools, 8 read-only structured resources (`tacp://device/*`, `tacp://storage/*`, `tacp://network/*`, `tacp://capabilities/list`), and 3 pre-configured agent prompts (`device-diagnostics`, `inspect-device`, `troubleshoot-network`).
4. **Android Bridge Companion**: Production-ready Android companion app skeleton (`companion/android-bridge`) providing accessibility-based gesture input and screen projection daemon on port 8989.
5. **Strict Governance & Auditing**: All mutating and executing capabilities respect `TACP_DEVICE_CONTROL`, `trust_profile`, `read_only_enforced`, and write immutable cryptographic audit trails.

---

## 2. Multi-Backend Execution Matrix

| Backend | Status | Privilege Level | Live Resolution / Notes |
| :--- | :--- | :--- | :--- |
| `termux` | **AVAILABLE** | `user` | Termux userspace active (prefix: /data/data/com.termux/files/usr, uid: 10316) |
| `android_shell` | **AVAILABLE** | `user` | Android /system/bin utilities active (15 verified tools) |
| `termux_api` | `companion_required` | `user` | Termux:API CLI is installed, but com.termux.api APK is not installed on Android host |
| `shizuku` | `unavailable` | `user` | Shizuku server is not running and rish CLI is not installed |
| `root` | `root_required` | `user` | Device is not rooted or su rejected authorization |
| `adb` | `unavailable` | `user` | adb binary not installed in Termux (install via 'pkg install android-tools') |
| `android_bridge` | `companion_required` | `user` | TACP Android Bridge companion app not running on localhost:8766 |

---

## 3. Capability Subsystem Breakdown (68 Capabilities)

- **Immediately Available (User Tier):** 53 capabilities
- **Companion Required (Termux:API / Android Bridge):** 11 capabilities
- **Shizuku / ADB Required:** 0 capabilities
- **Root Required:** 4 capabilities

### Subsystem Catalog

| Capability ID | Category | Backend Route | Availability | Description |
| :--- | :--- | :--- | :--- | :--- |
| `app.launch` | `app` | `android_shell` | **Available** | Launch an Android application by package name |
| `app.open_url` | `app` | `termux` | **Available** | Open URL or deep link in default browser / application |
| `automation.create` | `automation` | `termux` | **Available** | Define a reusable multi-step JSON capability workflow |
| `automation.list` | `automation` | `termux` | **Available** | List all registered workflow automations |
| `automation.start` | `automation` | `termux` | **Available** | Execute a registered automation workflow |
| `camera.capture` | `camera` | `none` | `companion_required` | Capture photo from camera and save to file |
| `camera.list` | `camera` | `none` | `companion_required` | Discover available hardware cameras (front/back) |
| `clipboard.get` | `clipboard` | `none` | `companion_required` | Read text from Android system clipboard |
| `clipboard.set` | `clipboard` | `none` | `companion_required` | Set text onto Android system clipboard |
| `device.battery` | `battery` | `android_shell` | **Available** | Query battery level, health, charging state, and temperature |
| `device.info` | `device` | `termux` | **Available** | Get device model, manufacturer, Android OS version, SDK level, CPU cores, RAM, and SELinux |
| `device.properties` | `device` | `android_shell` | **Available** | Query Android system properties (getprop) by key or list all |
| `device.snapshot` | `device` | `termux` | **Available** | Collect complete multi-domain state snapshot (hardware, OS, memory, storage roots, backends) |
| `device.uptime` | `device` | `termux` | **Available** | Return device uptime in seconds and human-readable format |
| `diagnostics.bundle` | `diagnostics` | `termux` | **Available** | Compile an archive (.zip) containing system telemetry, capability matrix, and logs |
| `filesystem.append` | `filesystem` | `termux` | **Available** | Append text content to existing or new file |
| `filesystem.copy` | `filesystem` | `termux` | **Available** | Copy file or directory tree to destination |
| `filesystem.delete` | `filesystem` | `termux` | **Available** | Delete file or directory (with recursive option) |
| `filesystem.find` | `filesystem` | `termux` | **Available** | Find files matching glob pattern recursively |
| `filesystem.hash` | `filesystem` | `termux` | **Available** | Compute SHA-256, MD5, or SHA-1 cryptographic hash of a file |
| `filesystem.list` | `filesystem` | `termux` | **Available** | List entries inside directory with size, modified time, and mode |
| `filesystem.mkdir` | `filesystem` | `termux` | **Available** | Create directory including parent directories |
| `filesystem.move` | `filesystem` | `termux` | **Available** | Move or rename file or directory |
| `filesystem.read` | `filesystem` | `termux` | **Available** | Read text or binary data from file with offset and limit protection |
| `filesystem.stat` | `filesystem` | `termux` | **Available** | Get detailed metadata, permissions, and file statistics |
| `filesystem.unzip` | `filesystem` | `termux` | **Available** | Extract zip archive to target directory |
| `filesystem.write` | `filesystem` | `termux` | **Available** | Write text or base64 data to target file path |
| `filesystem.zip` | `filesystem` | `termux` | **Available** | Compress file or directory into a zip archive |
| `input.capabilities` | `input` | `termux` | **Available** | Report which input simulation methods are currently usable |
| `input.key` | `input` | `none` | `root_required` | Inject Android hardware keyevent (e.g. KEYCODE_BACK, KEYCODE_HOME) |
| `input.tap` | `input` | `none` | `root_required` | Simulate touch tap at (x, y) coordinates (requires Shizuku or Accessibility) |
| `location.get` | `location` | `none` | `companion_required` | Get current GPS latitude, longitude, and accuracy |
| `logs.system` | `logs` | `android_shell` | **Available** | Retrieve recent logcat entries from Android system log buffer |
| `microphone.record` | `microphone` | `none` | `companion_required` | Record audio snippet from microphone |
| `network.diagnostics` | `network` | `termux` | **Available** | Run comprehensive network diagnostic check (interfaces, DNS, ping) |
| `network.download` | `network` | `termux` | **Available** | Download file from remote URL to local destination path |
| `network.http_request` | `network` | `termux` | **Available** | Execute structured HTTP request (GET, POST, PUT, DELETE) with headers and body |
| `network.interfaces` | `network` | `termux` | **Available** | Inspect active network interfaces and IP addresses |
| `network.ping` | `network` | `termux` | **Available** | Ping a remote IP or domain to test round-trip latency and packet loss |
| `network.resolve` | `network` | `termux` | **Available** | Perform DNS hostname resolution and return IP addresses |
| `notifications.post` | `notifications` | `none` | `companion_required` | Post an Android status bar notification |
| `package.info` | `package` | `android_shell` | **Available** | Inspect package APK size, DEX count, and manifest presence |
| `package.install` | `package` | `none` | `root_required` | Install APK package (requires Shizuku or root) |
| `package.list` | `package` | `android_shell` | **Available** | List installed Android packages (third-party, system, or all) |
| `package.path` | `package` | `android_shell` | **Available** | Get APK file location for an installed package |
| `package.uninstall` | `package` | `none` | `root_required` | Uninstall package from device (requires Shizuku or root) |
| `process.inspect` | `process` | `termux` | **Available** | Inspect command line, memory, status, and PPID of a specific process PID |
| `process.kill` | `process` | `termux` | **Available** | Terminate a running process PID with SIGKILL |
| `process.list` | `process` | `termux` | **Available** | List running Linux and Android processes with PID and command names |
| `process.signal` | `process` | `termux` | **Available** | Send an OS signal (e.g. 15 for SIGTERM, 9 for SIGKILL) to target PID |
| `screen.capture` | `screen` | `none` | `companion_required` | Capture screenshot of current display (requires MediaProjection or Root) |
| `screen.info` | `screen` | `android_shell` | **Available** | Query screen resolution, pixel density, and orientation |
| `sensors.list` | `sensors` | `none` | `companion_required` | List available hardware sensors (accelerometer, gyroscope, light, proximity) |
| `settings.get` | `settings` | `android_shell` | **Available** | Read system, secure, or global Android setting value |
| `shell.env` | `shell` | `termux` | **Available** | Inspect environment variables with sensitive secrets scrubbed |
| `shell.exec` | `shell` | `termux` | **Available** | Execute arbitrary Linux/Android command with arguments, working directory, and timeout |
| `shell.pwd` | `shell` | `termux` | **Available** | Return the current process working directory |
| `shell.which` | `shell` | `termux` | **Available** | Locate binary executable across PATH, /system/bin, /vendor/bin |
| `storage.cleanup_candidates` | `storage` | `termux` | **Available** | Scan for cache directories, temporary files, and dangling artifacts |
| `storage.duplicates` | `storage` | `termux` | **Available** | Detect duplicate files by matching size and cryptographic hashes |
| `storage.large_files` | `storage` | `termux` | **Available** | Discover files exceeding a specified size threshold (default: 50MB) |
| `storage.mounts` | `storage` | `termux` | **Available** | Inspect all mounted filesystems from /proc/mounts |
| `storage.overview` | `storage` | `termux` | **Available** | Inspect available storage roots, total/used/free space, and mount types |
| `tasks.cancel` | `tasks` | `termux` | **Available** | Cancel a running task |
| `tasks.get` | `tasks` | `termux` | **Available** | Get status, progress, and output of a specific task ID |
| `tasks.list` | `tasks` | `termux` | **Available** | List running and completed background tasks |
| `tts.speak` | `audio` | `none` | `companion_required` | Synthesize speech audio from text input |
| `wifi.status` | `wifi` | `none` | `companion_required` | Query Wi-Fi connection info and status |

---

## 4. MCP Protocol Integration Details

### Standard Resources (`resources/list`, `resources/read`)
- `tacp://device/info`: Live OS, build properties, SoC architecture, and memory breakdown
- `tacp://device/battery`: Battery health, current level, charging state, and temperature
- `tacp://device/properties`: Complete Android system build properties (`ro.build.*`, `ro.product.*`)
- `tacp://device/snapshot`: Fast holistic device telemetry snapshot
- `tacp://storage/overview`: Active storage partitions, emulated shared storage, and free space
- `tacp://network/interfaces`: Network interfaces, IP addresses, MTU, and flags
- `tacp://capabilities/list`: Machine-readable capability catalog and active backend bindings
- `tacp://system/health`: System daemon health, memory, and database status

### Standard Prompts (`prompts/list`, `prompts/get`)
- `device-diagnostics`: Automated workflow prompt instructing the agent to run full diagnostics across all device subsystems
- `inspect-device`: Telemetry overview prompt for rapid hardware and storage auditing
- `troubleshoot-network`: Automated connectivity and DNS troubleshooting prompt

---

## 5. Verification & Test Evidence

```
============================= 785 passed in 57.46s =============================
Unit Tests: 41 test files (test_device_control.py, test_policy_engine.py, etc.)
Integration Tests: 17 test files (test_cli.py, test_mcp_execution.py, test_streamable_http.py, etc.)
Security & Fuzzing: 11 test files (test_execution_security.py, test_path_traversal_baseline.py, etc.)
Live Subsystem Self-Test: 6/6 PASSED (shell, device, storage, network, package, diagnostics)
```

---

## 6. How to Connect Any AI Agent

### Local MCP Configuration (`antigravity-mcp-config.json`):
```json
{
  "mcpServers": {
    "tacp-android": {
      "command": "/data/data/com.termux/files/home/tacp/.venv/bin/python",
      "args": ["-m", "tacp.access.mcp.server", "--device-capabilities"],
      "env": {
        "TACP_DEVICE_CONTROL": "1",
        "TACP_TRUST_PROFILE": "BALANCED"
      }
    }
  }
}
```

### Remote Over HTTPS (Claude Desktop / Cursor):
```bash
export TACP_DEVICE_CONTROL=1
tacp remote start --port 8765
```

<!-- GOAL_COMPLETE -->