# TACP Phase 5: Adversarial Threat Model
**Document ID:** `TACP-THREAT-P5-001`  
**Classification:** Security Architecture  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Threat Landscape & Trust Assumptions

TACP runs inside the Android application boundary under Termux. In this environment, an autonomous AI model (or remote client invoking tools via MCP / CLI) acts as an untrusted or semi-trusted agent.

### 1.1 Threat Actors
1. **Compromised / Prompt-Injected LLM Agent:** Generates malicious tool call arguments (path traversal, command injection, output flooding, parameter tampering).
2. **Malicious Client / Remote Caller:** Attempts to bypass approval requirements, spoof caller identities, replay approval tokens, or exploit race conditions.
3. **Host Process / Local Neighbor:** Malicious files placed on the filesystem (e.g. rogue binaries in `/tmp` or workspace) attempting path/executable substitution.
4. **Denial-of-Service Vector:** Process output flooding, CPU exhaustion, fork bombs, disk filling.

---

## 2. Attack Vectors & Defensive Countermeasures

| ID | Attack Vector | Adversarial Mechanism | Defensive Countermeasure in TACP |
| :--- | :--- | :--- | :--- |
| **ATK-01** | Path Traversal | Using `../` or relative jumps in working directory or executable | Strict path resolution with `Path.resolve()`, verification with `target.is_relative_to(clean_root)` |
| **ATK-02** | Symlink Traversal | Symlinks pointing outside workspace root | Canonical realpath resolution; rejection of symlinks pointing outside workspace |
| **ATK-03** | Executable Substitution | Dropping a malicious binary named `printf` into `/tmp` or workspace | Canonical realpath validation ensuring executable resides strictly inside `SAFE_SEARCH_PATHS` (`/system/bin`, `/data/data/com.termux/files/usr/bin`) |
| **ATK-04** | Shell Injection | Passing shell metacharacters (`;`, `|`, `&&`, `` ` ``) in arguments | Direct argument vector execution via `subprocess.Popen(shell=False)` with zero shell invocation |
| **ATK-05** | Interpreter Escape | Requesting execution of `python`, `bash`, `node` | Explicit blacklist and strict whitelist (`printf`, `echo`, `true`); fail-closed validation |
| **ATK-06** | Output Flooding DoS | Generating gigabytes of stdout/stderr to exhaust RAM or burn CPU | Model B Output Governance: non-blocking stream reads into bytearray; immediate process group termination if byte limit is exceeded; status `OUTPUT_LIMIT_EXCEEDED` |
| **ATK-07** | Process Tree / Fork Escape | Child spawning background daemon or grandchildren | `start_new_session=True` creating a distinct process group; `os.killpg(pgid, SIGTERM/SIGKILL)` terminating the entire group |
| **ATK-08** | PID Reuse Vulnerability | Cancelling an old execution whose PID was recycled by the OS | In-memory active process tracking with spawn timestamps and proc stat validation before signal emission |
| **ATK-09** | Approval Replay / Reuse | Re-using an approval token for multiple executions | Atomic conditional SQL consumption (`UPDATE ... WHERE status='APPROVED'`); status set to `CONSUMED` in write transaction |
| **ATK-10** | Approval Parameter Substitution | Approving command A, then executing command B with token A | Cryptographic contract binding: approval ticket binds SHA-256 contract hash of all execution parameters |
| **ATK-11** | Environment Poisoning | Injecting `LD_PRELOAD`, `PYTHONPATH`, or API tokens into child environment | Safe Environment Allowlist: all caller variables must belong to an explicit safe allowlist; sensitive variables stripped |
| **ATK-12** | Audit Tampering | Modifying or deleting audit events to conceal malicious actions | Cryptographic SHA-256 hash chain (`previous_hash`); append-only SQLite schema; Merkle root consistency verification |
| **ATK-13** | Identity Spoofing | Claiming `principal.id = "operator"` to bypass approval gates | Privilege is tied strictly to `Role`, `TrustTier`, and explicit cryptographic credentials; string names confer zero privilege |
| **ATK-14** | Network Escape | Accessing LAN or internet when unauthorized | Policy engine rejects network-dependent capabilities; explicit documentation that network isolation is unenforced at kernel level |

---

## 3. Residual Risk & Out-of-Scope Risks

1. **Kernel Exploits:** Kernel vulnerabilities (privilege escalation to root) are out of scope; TACP assumes kernel integrity.
2. **Termux App Compromise:** If an attacker has full access to the Termux terminal session, they already hold the same UID permissions as TACP.
3. **Hardware / Power Loss:** Covered by SQLite WAL recovery and startup orphan reconciliation.
