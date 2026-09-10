# TACP Threat Model & Attack Surface Analysis

**Status**: INITIAL BASELINE  
**Standard**: STRIDE Methodology  

---

## 1. Primary Threat Categories

| Threat Vector | Category | Attack Scenario | Mitigation Strategy |
|---|---|---|---|
| **Path Traversal & Symlink Escape** | Elevation / Tampering | AI agent requests file write with `../../` or follows symlink to escape workspace. | Canonical path resolution; assertion that resolved path starts with workspace prefix. |
| **Command & Argument Injection** | Elevation / Tampering | Malicious shell metacharacters in file names or arguments (`; rm -rf`, ``). | Avoid `shell=True`; use explicit argument arrays (`execve`-style) and strict regex allowlists. |
| **Secret & Token Leakage** | Information Disclosure | Plaintext token logged to stdout, committed to Git, or returned in MCP tool output. | Automated pre-commit secret scans, environment variable redaction, and strict log sanitizers. |
| **Unrestricted MCP Invocation** | Spoofing / Elevation | Unauthorized local process or remote caller invokes privileged tools. | Mutual token authentication on MCP transports; per-call policy validation. |
| **Malicious Repository Instructions** | Tampering | Cloned repository contains poisoned prompt files, malicious git hooks, or rogue scripts. | Ignore repository-level instructions that contradict system constitution; sandboxed checkout. |
| **Resource Exhaustion (DoS)** | Denial of Service | Agent spawns infinite processes or fills disk partition (currently at 92%). | Process tree tracking, timeout enforcement, disk space guards before heavy writes. |

---

## 2. Trust Boundaries

- **Boundary 1 (External / MCP)**: Untrusted input arriving from network or IPC.
- **Boundary 2 (Intelligence / Policy)**: Agent generated parameters arbitrated by Control Plane.
- **Boundary 3 (Execution / OS)**: Python runtime interacting with Termux filesystem and subshells.
