# TACP Android Device Capability Report

**Generated:** 2026-09-24T19:58:45Z  
**Device:** VIVO V2348 (Platform: `crow`)  
**OS:** Android 16 (SDK 36, Patch: 2026-08-01)  
**Kernel / Arch:** Linux aarch64  
**TACP Version:** `0.4.0-rc.1` (Protocol: `2026-07-28`)  

---

## 1. Execution Backends & Privilege Matrix

| Backend | Availability | Privilege Level | Notes |
| :--- | :--- | :--- | :--- |
| `termux` | **AVAILABLE** | `user` | Native Termux sandbox process execution |
| `android_shell` | **AVAILABLE** | `user` | Standard Android /system/bin binaries in user sandbox |
| `termux_api` | `companion_apk_required` | `N/A` | Install com.termux.api APK from F-Droid to enable Termux API bridge |
| `shizuku` | `unavailable` | `N/A` | Shizuku server is not running and rish CLI is not installed |
| `root` | `su_failed` | `N/A` | No su program found on this device. Termux
does not supply tools for rooting, see e.g.
http://www.androidcentral.com/root for
information about rooting Android. |
| `adb` | `unavailable` | `N/A` | Local ADB daemon not connected |
| `android_bridge` | `not_installed` | `N/A` | TACP Android Bridge companion application not running on localhost:8766 |
| `accessibility` | `companion_required` | `N/A` | Requires TACP Android Bridge companion app with Accessibility Service enabled |
| `media_projection` | `companion_required` | `N/A` | Requires TACP Android Bridge companion app with Screen Capture permission |

---

## 2. Hardware & Resource Metrics

- **CPU Cores:** 8 cores (`aarch64`)
- **RAM (Total / Available):** 7305 MB / 1288 MB
- **Primary Storage Free:** 7.89 GB
- **SELinux Mode:** `Unknown (Enforcing assumed)`
- **Termux UID / GID:** `uid=10316, gid=10316`

---

## 3. Storage Mounts & Filesystem Roots

| Label | Path | Type | Writable | Total | Free | Used % |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `termux-home` | `/data/data/com.termux/files/home` | app-private | YES | 102.72 GB | 7.89 GB | 92.2% |
| `termux-prefix` | `/data/data/com.termux/files/usr` | app-binaries | YES | 102.72 GB | 7.89 GB | 92.2% |
| `shared-storage` | `/storage/emulated/0` | user-accessible | YES | 102.72 GB | 7.89 GB | 92.2% |
| `emulated-root` | `/storage/emulated` | system-fuse | NO (Read-only) | 102.72 GB | 7.89 GB | 92.2% |
| `data-partition` | `/data` | system-data | NO (Read-only) | 102.72 GB | 7.89 GB | 92.2% |
| `system-partition` | `/system` | system-os | NO (Read-only) | 4.36 GB | 0.0 GB | 100.0% |

---

## 4. Installed Android Applications (Sample)

Discovered third-party packages installed on user 0:

- `in.gov.uidai.facerd`
- `r.rural.awaasplus_2_0`
- `com.vibzcode.niabrowser`
- `com.moonshot.kimichat`
- `net.one97.paytm`
- `com.chrome.dev`
- `com.apkmirror.helper.prod`
- `com.reddit.frontpage`
- `com.jrzheng.supervpnpayment`
- `com.pinterest`
- `org.chromium.webapk.ac0902708c826ca2f_v2`
- `com.google.android.apps.docs.editors.docs`
- `com.large.big.app.icon.widgets.android.launcher.giganticon`
- `uz.unnarsx.cherrygram`
- `app.revanced.android.youtube`
- `com.dts.freefiremax`
- `com.zoho.mail`
- `com.kratosle.unlim`
- `com.openai.chatgpt`
- `com.jaiho.spins.fun`

---

## 5. Next Steps for Capability Expansion

1. **Termux:API Companion**: To enable native hardware sensors, camera, telephony, and SMS, install `com.termux.api` APK from F-Droid.
2. **Shizuku / ADB Privileges**: For rootless package installation, input injection, and full dumpsys, activate Shizuku via Wireless Debugging (`adb pair localhost:PORT`).
3. **TACP Android Bridge**: Build and run the `android-bridge` companion for Accessibility UI tree extraction and MediaProjection live screen capture.