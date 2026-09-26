# Connecting AI Agents to TACP Android Control Plane

TACP transforms your Android device into a standards-compliant Model Context Protocol (MCP) server, offering **68 deep device capabilities** across 9 subsystems with strict policy controls and zero fake success.

---

## 1. Quick Verification on Device

Before connecting an external agent, verify your local installation and device health:

```bash
cd /data/data/com.termux/files/home/tacp
source .venv/bin/activate

# 1. Run full subsystem self-test
tacp self-test --json

# 2. Inspect active device capabilities
tacp capabilities --device

# 3. Check health and backends
tacp doctor --json
```

---

## 2. Connecting Antigravity (AGY) / Local Agent (Stdio)

If your AI assistant is running locally in Termux or in a shared container on the device:

Add the following to your Antigravity or MCP client configuration (`~/.gemini/antigravity/mcp_servers.json` or equivalent):

```json
{
  "mcpServers": {
    "tacp-android": {
      "command": "/data/data/com.termux/files/home/tacp/.venv/bin/python",
      "args": [
        "-m",
        "tacp.access.mcp.server",
        "--device-capabilities"
      ],
      "env": {
        "TACP_DEVICE_CONTROL": "1",
        "TACP_TRUST_PROFILE": "BALANCED",
        "PATH": "/data/data/com.termux/files/usr/bin:/system/bin:/system/xbin"
      }
    }
  }
}
```

---

## 3. Remote Connection (Claude Desktop / Cursor / Remote Agents)

To give a remote AI agent running on your laptop or cloud access to this Android device over HTTPS:

### Step 1: Start the Remote Daemon with Device Capabilities

```bash
cd /data/data/com.termux/files/home/tacp
source .venv/bin/activate

export TACP_DEVICE_CONTROL=1
export TACP_REMOTE_ENABLED=1
export TACP_TRUST_PROFILE=BALANCED

tacp remote start --port 8765
```

This generates an authorization pairing token and displays your public endpoint (via Cloudflare tunnel or local port).

### Step 2: Configure Client

In **Claude Desktop** (`claude_desktop_config.json`) or **Cursor** (`settings.json`):

```json
{
  "mcpServers": {
    "my-android-phone": {
      "url": "https://<your-subdomain>.trycloudflare.com/mcp",
      "headers": {
        "Authorization": "Bearer <YOUR_TACP_TOKEN>"
      }
    }
  }
}
```

---

## 4. MCP Subsystems Exposed

Once connected, your AI agent automatically receives:

### Tools (80+ Tools)
- **Device & System**: `device.info`, `device.snapshot`, `device.battery`, `device.properties`, `device.uptime`
- **Shell & Execution**: `shell.exec`, `shell.which`, `shell.pwd`, `process.list`, `process.kill`
- **Filesystem & Storage**: `storage.overview`, `storage.mounts`, `storage.large_files`, `storage.cleanup_candidates`, `fs.read`, `fs.write`, `fs.list`, `fs.zip`
- **Applications**: `package.list`, `package.info`, `package.path`, `app.launch`, `app.open_url`
- **Network & Diagnostics**: `network.interfaces`, `network.ping`, `network.dns_lookup`, `network.http_probe`, `network.wifi_info`, `diagnostics.bundle`
- **Automation & Hardware**: `automation.create`, `automation.start`, `camera.list`, `camera.capture`, `screen.capture`, `tts.speak`, `notification.post`

### Resources (`resources/list`, `resources/read`)
- `tacp://device/info` - Real-time device specifications & OS details
- `tacp://device/battery` - Power levels, charging status & temperature
- `tacp://device/properties` - Android system build properties
- `tacp://device/snapshot` - High-level system state & memory metrics
- `tacp://storage/overview` - Storage mounts, total/used/free space
- `tacp://network/interfaces` - Network interfaces & IP addresses
- `tacp://capabilities/list` - Live capability & backend availability matrix

### Prompts (`prompts/list`, `prompts/get`)
- `device-diagnostics` - Initiates full end-to-end device diagnostic workflow
- `inspect-device` - Pre-packaged health and telemetry inspection
- `troubleshoot-network` - Automated connectivity & DNS diagnostic routine

---

## 5. Privilege & Companion Upgrades

TACP enforces zero fake success. Features requiring higher privileges report clear instructions:

| Privilege Tier | Unlocks | Enabling Mechanism |
| :--- | :--- | :--- |
| **User (Active)** | 35+ capabilities (shell, read/write, apps, network, diagnostics) | Active by default in Termux |
| **Termux:API** | Battery, Camera, SMS, TTS, Contacts, Wi-Fi | `pkg install termux-api` & install `Termux:API` APK from F-Droid |
| **Android Bridge** | Accessibility tap/swipe/type, screen projection | Build & install `companion/android-bridge/` APK |
| **Shizuku / ADB** | Permission grants, system service dumpsys, package force-stop | Start Shizuku app (`rish`) or connect wireless ADB |
| **Root (su)** | Kernel module loading, raw disk access, SELinux override | Magisk / KernelSU |
