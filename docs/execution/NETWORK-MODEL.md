# TACP Network Model Specification
## Strict Default Deny, Exfiltration Defense & Network Boundary Realities

- **Standard:** TACP-SPEC-004-NET
- **Status:** APPROVED SPECIFICATION (GATE A)
- **Phase:** Phase 4 — Controlled Command Execution
- **Target OS:** Android 13 / Termux (aarch64)

---

## 1. Core Mandate: Default-Deny Network Egress

A primary risk of granting operating-system command execution to AI agents is network-based abuse:
1. **Data Exfiltration:** Reading confidential files, keys, or source code and transmitting them via HTTP POST, DNS tunneling, or raw TCP sockets.
2. **Reverse Shells:** Establishing outbound TCP connections (`nc -e`, `bash -i >& /dev/tcp/...`, `python -c ... socket ...`) to transfer control to an external attacker.
3. **Payload Download:** Pulling malicious second-stage binaries or scripts from untrusted external URLs (`curl | sh`).
4. **Internal Network Scanning / SSRF:** Probing `localhost` (127.0.0.1) services, Android system sockets, or local private subnet devices (192.168.x.x, 10.x.x.x).

**Constitutional Axiom:**
> **"Command execution shall default to NETWORK DENIED (`network_enabled = False`). No process shall be granted network egress unless explicit network policy, capability, and human approval are configured."**

---

## 2. Operating System Realities on Android / Termux

In enterprise Linux environments, process network isolation is typically enforced via **network namespaces** (`ip netns`, Docker bridge networks) or **eBPF socket filtering**.

On Android within Termux:
- Network namespaces require kernel `CONFIG_NET_NS` and `CAP_NET_ADMIN` (root privilege).
- An unprivileged Android user application cannot create isolated network namespaces or bind custom iptables / nftables rules.
- Any process spawned with regular UID permissions inherits standard Android internet socket permissions (`android.permission.INTERNET`).

### The Architectural Defense:
Because unprivileged network namespaces are unavailable without root:
1. **Executable Whitelisting:** Utilities with primary network functions (`curl`, `wget`, `nc`, `ncat`, `socat`, `ssh`, `scp`, `telnet`, `ftp`, `rsync`) are **strictly excluded** from the permitted execution whitelist in Phase 4.
2. **Interpreter Exclusion:** General-purpose scripting runtimes (`python`, `node`, `ruby`, `perl`, `bash`, `sh`) that can open raw sockets via standard libraries are excluded from the initial execution vertical slice.
3. **Deterministic Local Primitives:** The initial vertical slice is restricted to deterministic, local computational binaries (`printf`, `echo`) that possess no network socket opening logic.
4. **Policy Enforcement:** If any request sets `network_enabled=True` when `config.network_enabled=False`, the request is denied immediately in Stage 2 with `TacpSecurityError(ErrorCode.POLICY_DENIED)`.

---

## 3. Network Policy State & Configuration

In `TacpConfig`:
```python
network_enabled: bool = False  # Controlled via TACP_NETWORK_ENABLED
remote_execution_enabled: bool = False  # Controlled via TACP_REMOTE_EXECUTION_ENABLED
```

Both flags default to `False`. Neither database migrations nor routine configuration initialization will alter these defaults.

---

## 4. Future Architecture for Governed Network Execution

When network-dependent tools (such as package managers or git operations) are introduced in future phases, network governance will be enforced through:
1. **Governed HTTP/S Egress Proxy:** Directing all external traffic through a local TACP proxy that enforces domain whitelisting, audit logging, and payload inspection.
2. **Domain-Specific Scoping:** Requiring human approval tickets that specify the exact target domain and port (e.g. `pypi.org:443`).
3. **DNS Query Inspection:** Logging and restricting DNS resolutions to approved domains.
