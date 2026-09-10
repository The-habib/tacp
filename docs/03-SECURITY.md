# TACP Security Principles & Architecture

**Status**: BASELINE ESTABLISHED  
**Security Lead**: Antigravity Security Lead  

---

## 1. Fundamental Security Invariants

1. **Zero-Trust Input**: All requests, inputs, files, and MCP payloads are untrusted until validated against strict schemas.
2. **Default-Deny Policy**: Any operation not explicitly permitted by an active capability lease or policy rule is rejected.
3. **Zero Secrets in Code**: Secrets, API keys, and credentials must never exist in repository code, tests, documentation, or environment dumps.
4. **Least Privilege Execution**: TACP runs strictly within the unprivileged Android application user context (`u0_a316` / `untrusted_app_27`). Root elevation (`su`) is prohibited.
5. **Fail-Closed Architecture**: Any error in authentication, policy resolution, or path validation must immediately fail closed and terminate the action.

---

## 2. Workspace Sandboxing & Path Invariants

All file and execution operations must be strictly scoped to registered workspaces:
- Paths must be canonicalized and checked against directory traversal (`..`).
- Symlinks pointing outside the designated workspace root are rejected.
- Direct manipulation of Termux internal configuration (`~/.termux`, `~/.gemini`, `/data/data/com.termux/files/usr/etc`) is blocked.

---

## 3. Defense-in-Depth Layers

1. **Network Layer**: Local loopback binding only by default; authenticated TLS tunnels for remote access.
2. **Protocol Layer**: Strict MCP JSON-RPC schema validation.
3. **Application Layer**: Policy engine and capability leasing.
4. **Filesystem Layer**: Path jail and canonicalization checks.
5. **OS Layer**: Android SELinux domain containment.
