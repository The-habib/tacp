# TACP Execution Threat Model
## Adversarial Analysis for Controlled Command Execution

- **Standard:** TACP-THREAT-004
- **Status:** APPROVED THREAT SPECIFICATION (GATE A)
- **Phase:** Phase 4 — Controlled Command Execution
- **Target Platform:** Android 13 / Termux (Linux kernel 5.15.197 aarch64)

---

## 1. Scope & Objective

This threat model identifies potential threat actors, attack surfaces, vulnerability classes, and defensive boundaries introduced by controlled operating-system process execution in TACP.

---

## 2. Threat Actors & Adversarial Capabilities

```
+-----------------------------------------------------------------------------------+
|                            THREAT ACTOR MATRIX                                    |
+---+----------------------------+-----------------------------+--------------------+
|ID | Threat Actor               | Capabilities / Access       | Primary Objective  |
+---+----------------------------+-----------------------------+--------------------+
|A  | Hallucinating Model        | Valid MCP connection        | Accidental damage  |
|B  | Prompt-Injected Agent      | Adversarial LLM input       | Sandbox escape     |
|C  | Malicious Repository       | Untrusted workspace code    | Supply chain RCE   |
|D  | Untrusted Remote Caller    | Tunnel / network API access | Unauthorized exec  |
|E  | Runaway / Loop Model       | Automated repetitive calls  | DoS / fork bomb    |
|F  | Malicious Child Process    | Spawned process execution   | Orphan persistence |
|G  | Multi-Tenant / Cross-Agent | Concurrently active agents  | Cross-talk/spoof   |
+---+----------------------------+-----------------------------+--------------------+
```

### Actor A: Hallucinating / Confused Model
- **Description:** A well-intentioned model generating incorrect syntax, malformed flags, wrong working directories, or invalid paths due to hallucination or misunderstanding.
- **Attack Vector:** Submitting malformed flags (e.g. `rm -rf /`, typoed paths, recursive commands, unintended shell operators).
- **Defense:** Strict input validation, default-deny path containment, dry-run previews, human approval requirement, non-destructive command whitelist.

### Actor B: Adversarial Prompt-Injected Model
- **Description:** An LLM whose system prompt or context has been hijacked via indirect prompt injection (e.g. from reading an untrusted file, web page, or issue description).
- **Attack Vector:** Crafting payload strings containing shell metacharacters (`; rm -rf`, `| nc`, `` `id` ``), attempting to invoke interpreters (`python -c`, `bash -c`), escaping workspace boundaries via `../` traversal, or injecting malicious environment variables (`LD_PRELOAD`, `PYTHONPATH`).
- **Defense:**
  1. Complete elimination of shell interpreters (`shell=False`, no `bash -c`).
  2. Strict `argv: List[str]` tokenization.
  3. Rejection of interpreter evaluation flags (`-c`, `-e`).
  4. Environment stripping (purging `LD_*`, `PYTHON*`, secrets).
  5. Canonical contract hashing binding exact arguments to human approval.

### Actor C: Malicious Workspace Repository (Clone / Open Attack)
- **Description:** A repository cloned from an untrusted source containing malicious `.git` hooks, smudge/clean filters, executable symlinks, or trojanized helper scripts.
- **Attack Vector:** Convincing the agent to execute a command that triggers git hooks, follows symlinks to `/data/data/com.termux/files/usr/bin`, or executes an unvetted local binary.
- **Defense:**
  1. Protection of `.git` directory and metadata patterns from modification.
  2. Resolving symlinks and checking realpath boundaries.
  3. Stripping `GIT_CONFIG`, `GIT_SSH`, and git helper variables from the process environment.
  4. Whitelisting only trusted system binaries in initial vertical slices.

### Actor D: Untrusted Network Caller / Compromised Remote Client
- **Description:** An external entity attempting to reach the TACP control plane over a network tunnel (e.g. ngrok, cloudflare tunnel) or compromised IDE bridge.
- **Attack Vector:** Replaying old approval tokens, spoofing `Principal` identity, calling mutating tools when feature flags are disabled, attempting remote execution.
- **Defense:**
  1. `remote_execution_enabled = False` by default.
  2. `Principal` trust tier verification (agents and unverified callers are `RESTRICTED` or `UNTRUSTED`).
  3. Single-use token consumption preventing replay attacks.
  4. Cryptographic correlation of caller identity with request context.

### Actor E: Runaway / Loop-Executing Model
- **Description:** An autonomous loop or agent stuck in an infinite retry or failure cycle rapidly issuing execution requests.
- **Attack Vector:** Resource exhaustion, database flooding, disk filling via log generation, CPU starvation, PID exhaustion (fork bomb).
- **Defense:**
  1. Single-concurrency execution locks.
  2. Output limits on stdout/stderr (64 KB cap with automatic truncation).
  3. Non-negotiable watchdog timeouts (default 15s).
  4. Refusal of autonomous execution loops in Phase 4.

### Actor F: Malicious Child Process / Exploit Payload
- **Description:** A spawned process attempting to escape containment by detaching from its parent, persisting in the background, or killing unrelated processes.
- **Attack Vector:** Calling `fork()` to orphan descendants, catching `SIGTERM`, ignoring signals, waiting for parent termination to become a daemon, or guessing PIDs to terminate unrelated user tasks.
- **Defense:**
  1. Launching all processes with `start_new_session=True` (`os.setsid()`), establishing a new process group.
  2. Terminating the entire process group via `os.killpg(pgid, SIGTERM)` followed by `SIGKILL`.
  3. Refusing to allow child processes to accept interactive input (`stdin=DEVNULL`).
  4. Scoping cancellation and termination strictly to TACP-recorded process groups.

### Actor G: Multi-Tenant / Cross-Agent Boundary Confusion
- **Description:** Multiple concurrent agents or background tasks submitting requests simultaneously.
- **Attack Vector:** Cross-agent token theft, race conditions during ticket approval, audit log forking, workspace cross-contamination.
- **Defense:**
  1. Atomic SQLite transactions (`BEGIN IMMEDIATE`) on approvals, locks, and audit appends.
  2. Strict workspace directory jailing.
  3. Ticket binding to `workspace_id`, `principal_id`, and `contract_hash`.

---

## 3. Explicit Security Boundaries: What TACP Can and Cannot Defend Against

### What TACP CAN Defend Against:
1. **Shell Injection:** Fully mitigated by `shell=False` and array-based `argv` passing.
2. **Path Traversal & Escape:** Fully mitigated by canonical `realpath()` validation against workspace roots.
3. **Environment Poisoning:** Fully mitigated by constructing an explicit minimal whitelist environment.
4. **Secret Leaking:** Fully mitigated by scrubbing environment keys containing secrets, tokens, or credentials.
5. **Output Flooding:** Fully mitigated by memory-bounded buffered readers and truncation flags.
6. **Hung Processes:** Fully mitigated by process-group watchdog timers and escalatory `SIGTERM` -> `SIGKILL` termination.
7. **Approval Replay:** Fully mitigated by single-use token consumption and cryptographic contract hashing.
8. **Audit Forking:** Fully mitigated by `BEGIN IMMEDIATE` transaction serialization on append.

### What TACP CANNOT Defend Against (Operating-System Realities on Android/Termux):
1. **Compromised Same-UID Host Environment:** Termux runs in a single Android application sandbox under a single Linux UID (e.g. `u0_a316`). TACP is an **application-level control plane**, NOT a hardware or kernel hypervisor. Any process running as `u0_a316` possesses identical POSIX filesystem and process inspection permissions as TACP itself.
2. **Direct Memory Corruption / Kernel Exploits:** If an executed binary contains a kernel zero-day privilege escalation exploit that targets the Linux kernel, TACP cannot prevent OS-level compromise.
3. **Hardware-Level Power Off / Kill:** If Android's Low Memory Killer (LMK) or the user force-stops Termux, TACP processes are terminated abruptly.
4. **Side-Channel Attacks:** TACP does not provide hardware cache isolation between processes running on the same CPU cores.

---

## 4. Threat Summary & Gate A Conclusion

The threat analysis demonstrates that process execution can be safely governed at the application layer if and only if:
- Shell strings are entirely abolished.
- Executables are strictly vetted and whitelisted.
- Process groups are created and forcibly cleaned up on exit or timeout.
- Human approval is single-use and bound cryptographically to all parameters.
