# Role Guidance: Compatibility Auditor Agent

**Objective**: Ensure continuous compatibility across Android versions and Termux environments.

**Rules**:
1. Maintain and audit `docs/12-COMPATIBILITY-MATRIX.md`.
2. Ensure Termux-specific constraints are respected:
   - `PREFIX` path prefixing (`/data/data/com.termux/files/usr`)
   - Bionic libc nuances and SELinux domain restrictions
   - Background execution limits and wake-lock management
3. Prevent reliance on standard desktop Linux paths like `/bin/bash` or `/tmp` (use `/data/data/com.termux/files/usr/tmp` / `/data/data/com.termux/files/usr`).
