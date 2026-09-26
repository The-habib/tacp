# TACP Android Bridge Companion App

The **TACP Android Bridge Companion** is a lightweight, non-invasive Android companion service designed for Termux environments where full ADB or Root privileges may not be active.

It leverages standard Android APIs (Accessibility Service and MediaProjection) to expose local automation and screen inspection over a secure local HTTP daemon (`http://127.0.0.1:8989`).

---

## Capabilities Provided

| Capability | Backend Route | Android Mechanism |
| :--- | :--- | :--- |
| `automation.tap` | `POST /tap` | `AccessibilityService.dispatchGesture` |
| `automation.swipe` | `POST /swipe` | `AccessibilityService.dispatchGesture` |
| `automation.key` | `POST /key` | `AccessibilityService.performGlobalAction` |
| `automation.type` | `POST /text` | `AccessibilityNodeInfo.ACTION_SET_TEXT` |
| `automation.dump_hierarchy` | `GET /dump` | `AccessibilityService.rootInActiveWindow` |
| `automation.screenshot` | `GET /screenshot` | `MediaProjection` Virtual Display Framebuffer |

---

## Building and Installing

### 1. Build using Gradle (Android Studio or CLI)

```bash
cd companion/android-bridge
./gradlew assembleDebug
```

Output APK will be generated at:
`companion/android-bridge/app/build/outputs/apk/debug/app-debug.apk`

### 2. Install on Device

Using ADB:
```bash
adb install -r companion/android-bridge/app/build/outputs/apk/debug/app-debug.apk
```

Or copy the APK to device storage and install via the Android Package Installer.

### 3. Grant Required Permissions

1. Open the **TACP Bridge** app.
2. Tap **Enable Accessibility Service** -> Navigate to **Downloaded Services** -> Enable **TACP Android Bridge**.
3. Tap **Start Screen Capture** -> Grant screen projection dialog permission.

### 4. Verification

From Termux:
```bash
curl -H "Authorization: Bearer tacp-bridge-local-token" http://127.0.0.1:8989/health
```

Expected output:
```json
{
  "status": "ok",
  "service": "tacp-android-bridge",
  "version": "1.0.0",
  "accessibility_enabled": true,
  "screen_capture_enabled": true,
  "port": 8989
}
```
