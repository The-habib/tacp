# Phase 4 Evidence — Physical Device Verification (Android / Termux)

**Document ID**: TACP-EV-P4-13  
**Status**: VERIFIED  
**Target Release**: v0.4.0-rc.1  

## 1. Environment Characteristics
- **Architecture**: `aarch64`
- **OS**: Linux / Android 13 (`linux` kernel)
- **Termux Prefix**: `/data/data/com.termux/files/usr`
- **Python**: 3.14.6 (`.venv`)

## 2. On-Device Validation Results
- `tests/device/test_termux_execution.py`:
  - `test_device_printf_live_execution`: **PASS** (Live execution of `/data/data/com.termux/files/usr/bin/printf`)
  - `test_device_echo_live_execution`: **PASS** (Live execution of `/data/data/com.termux/files/usr/bin/echo`)
  - `test_device_true_live_execution`: **PASS** (Live execution of `/data/data/com.termux/files/usr/bin/true`)
  - `test_device_disallowed_shell_binaries_rejected`: **PASS** (`sh`, `bash`, `python`, `python3` rejected fail-closed)
  - `test_device_environment_sanitation`: **PASS** (`LD_PRELOAD`, `PYTHONPATH`, AWS keys stripped)
- `tests/device/test_termux_device.py`: **7/7 PASS**
- Process group setsid isolation and signal delivery confirmed operational on Android kernel without permission denials.
