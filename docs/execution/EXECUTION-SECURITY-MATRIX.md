# TACP Execution Security Matrix
## Comprehensive Attack Scenario & Defense Verification Matrix (100+ Cases)

- **Standard:** TACP-TEST-004-MATRIX
- **Status:** APPROVED TEST SPECIFICATION (GATE A)
- **Phase:** Phase 4 — Controlled Command Execution
- **Target Test Suite:** `tests/security/test_execution_security.py`

---

## 1. Overview & Verification Philosophy

This matrix defines the 100+ attack scenarios, adversarial vectors, boundary abuse cases, and concurrency race conditions that TACP's execution subsystem must detect, block, and log.

Each test is categorized by **Vector ID**, **Category**, **Attack Payload / Scenario**, **Mitigating Component**, **Expected Result**, and **Audit Log Verification**.

---

## 2. Master Security Test Matrix

| ID | Category | Attack Payload / Scenario | Mitigating Component | Expected Result |
| :--- | :--- | :--- | :--- | :--- |
| **SEC-01** | Shell Injection | Semicolon delimiter: `printf "foo; id"` | Executor (`shell=False`) | Output literal string `foo; id`, no shell execution |
| **SEC-02** | Shell Injection | Ampersand backgrounding: `printf "foo & calc"` | Executor (`shell=False`) | Output literal string `foo & calc` |
| **SEC-03** | Shell Injection | Unix pipe: `printf "foo | cat /etc/passwd"` | Executor (`shell=False`) | Output literal string `foo \| cat ...` |
| **SEC-04** | Shell Injection | Backticks: ``printf "foo `id`"`` | Executor (`shell=False`) | Output literal string `foo \`id\`` |
| **SEC-05** | Shell Injection | Subshell substitution: `printf "$({whoami})"` | Executor (`shell=False`) | Output literal string `$({whoami})` |
| **SEC-06** | Shell Injection | Newline command injection: `printf "foo\nid"` | Executor (`shell=False`) | Output literal string with newline |
| **SEC-07** | Shell Injection | Double ampersand: `printf "foo && id"` | Executor (`shell=False`) | Output literal string |
| **SEC-08** | Shell Injection | Double pipe: `printf "foo || id"` | Executor (`shell=False`) | Output literal string |
| **SEC-09** | Shell Injection | Redirect out: `printf "foo > /data/.../bad"` | Executor (`shell=False`) | Output literal string, no file created |
| **SEC-10** | Shell Injection | Redirect append: `printf "foo >> file"` | Executor (`shell=False`) | Output literal string, no append |
| **SEC-11** | Shell Injection | Redirect in: `cat < /etc/passwd` | Executor (`shell=False`) | Treated as literal argv, no redirection |
| **SEC-12** | Shell Injection | Here-doc: `printf "<<EOF\nfoo\nEOF"` | Executor (`shell=False`) | Output literal string |
| **SEC-13** | Shell Injection | Tilde expansion: `printf "~/secrets"` | Executor (`shell=False`) | Output literal string, no tilde expansion |
| **SEC-14** | Shell Injection | Variable expansion: `printf "$HOME"` | Executor (`shell=False`) | Output literal `$HOME`, no expansion |
| **SEC-15** | Shell Injection | Escaped quotes: `printf "\" ; id ; \""` | Executor (`shell=False`) | Output literal escaped quotes |
| **SEC-16** | Argument Injection | Option injection: `-oProxyCommand=calc` | Argument Validator | Strict option validation / safe argv |
| **SEC-17** | Path Poisoning | Relative `PATH` injection: `PATH=.:$PATH` | Environment Assembler | Overwritten by curated system `PATH` |
| **SEC-18** | Path Poisoning | Empty directory in `PATH`: `PATH=:/bin` | Environment Assembler | Overwritten by curated system `PATH` |
| **SEC-19** | Path Poisoning | Untrusted directory in `PATH`: `PATH=/tmp` | Environment Assembler | Overwritten by curated system `PATH` |
| **SEC-20** | Path Traversal | Target executable traversal: `../../bin/sh` | Executable Resolver | `TacpSecurityError(PATH_TRAVERSAL)` |
| **SEC-21** | Path Traversal | Working directory traversal: `cwd=../../` | Workspace Service | `TacpSecurityError(WORKSPACE_ESCAPE)` |
| **SEC-22** | Path Traversal | Deep working directory escape: `a/b/../../../../` | Workspace Service | `TacpSecurityError(WORKSPACE_ESCAPE)` |
| **SEC-23** | Symlink Attack | Executable is symlink to `/system/bin/sh` | Executable Resolver | `TacpSecurityError(FORBIDDEN_EXECUTABLE)` |
| **SEC-24** | Symlink Attack | Working dir is symlink pointing to `/data/data/...` | Workspace Service | `TacpSecurityError(WORKSPACE_ESCAPE)` |
| **SEC-25** | Symlink Attack | Broken symlink as target executable | Executable Resolver | `TacpNotFoundError(EXECUTABLE_NOT_FOUND)` |
| **SEC-26** | Interpreter Abuse | `python -c "import os; os.system('id')"` | Executable Resolver / Policy | Rejected: Python interpreter not permitted |
| **SEC-27** | Interpreter Abuse | `python -m pytest ... -o ...` | Policy Engine | Rejected: Python not permitted in Slice 1 |
| **SEC-28** | Interpreter Abuse | `bash -c "id"` | Executable Resolver / Policy | Rejected: Shell interpreter forbidden |
| **SEC-29** | Interpreter Abuse | `sh -c "id"` | Executable Resolver / Policy | Rejected: Shell interpreter forbidden |
| **SEC-30** | Interpreter Abuse | `node -e "process.exit()"` | Executable Resolver / Policy | Rejected: Node interpreter forbidden |
| **SEC-31** | Interpreter Abuse | `perl -e "system('id')"` | Executable Resolver / Policy | Rejected: Perl interpreter forbidden |
| **SEC-32** | Interpreter Abuse | `ruby -e "system('id')"` | Executable Resolver / Policy | Rejected: Ruby interpreter forbidden |
| **SEC-33** | Interpreter Abuse | `env bash` | Executable Resolver | `env` binary not permitted |
| **SEC-34** | Interpreter Abuse | Executing executable with `.py` extension | Executable Resolver | Rejected: Script invocation disallowed |
| **SEC-35** | Interpreter Abuse | Executing script with `.sh` extension | Executable Resolver | Rejected: Script invocation disallowed |
| **SEC-36** | Environment Poisoning | Injecting `LD_PRELOAD=/tmp/evil.so` | Environment Assembler | Variable unconditionally stripped |
| **SEC-37** | Environment Poisoning | Injecting `LD_LIBRARY_PATH=/tmp` | Environment Assembler | Variable unconditionally stripped |
| **SEC-38** | Environment Poisoning | Injecting `PYTHONPATH=/tmp` | Environment Assembler | Variable unconditionally stripped |
| **SEC-39** | Environment Poisoning | Injecting `PYTHONHOME=/tmp` | Environment Assembler | Variable unconditionally stripped |
| **SEC-40** | Environment Poisoning | Injecting `NODE_PATH=/tmp` | Environment Assembler | Variable unconditionally stripped |
| **SEC-41** | Environment Poisoning | Injecting `CLASSPATH=/tmp` | Environment Assembler | Variable unconditionally stripped |
| **SEC-42** | Environment Poisoning | Injecting `RUBYLIB=/tmp` | Environment Assembler | Variable unconditionally stripped |
| **SEC-43** | Environment Poisoning | Injecting `PERL5LIB=/tmp` | Environment Assembler | Variable unconditionally stripped |
| **SEC-44** | Environment Poisoning | Injecting `BASH_ENV=/tmp/rc` | Environment Assembler | Variable unconditionally stripped |
| **SEC-45** | Secret Leaking | Inheriting `OPENAI_API_KEY` from parent | Environment Assembler | Variable unconditionally stripped |
| **SEC-46** | Secret Leaking | Inheriting `ANTHROPIC_API_KEY` from parent | Environment Assembler | Variable unconditionally stripped |
| **SEC-47** | Secret Leaking | Inheriting `GITHUB_TOKEN` from parent | Environment Assembler | Variable unconditionally stripped |
| **SEC-48** | Secret Leaking | Inheriting `TACP_DATABASE_PASSWORD` | Environment Assembler | Variable unconditionally stripped |
| **SEC-49** | Secret Leaking | Inheriting `AWS_SECRET_ACCESS_KEY` | Environment Assembler | Variable unconditionally stripped |
| **SEC-50** | File Descriptor Leak | Open DB file descriptor inherited by child | ProcessExecutor (`close_fds=True`) | Verified: Child has no access to parent FDs |
| **SEC-51** | Stdin Injection | Attempting interactive input via stdin | ProcessExecutor (`stdin=DEVNULL`) | Immediate EOF on stdin |
| **SEC-52** | Output Flooding | Infinite loop: `yes "A"` | Stream Reader | Truncated at 64 KB, terminated via timeout |
| **SEC-53** | Output Flooding | Single huge line: 1 MB without newlines | Stream Reader | Truncated at 64 KB, memory bounded |
| **SEC-54** | Output Flooding | Giant stderr stream | Stream Reader | Truncated at 64 KB |
| **SEC-55** | Watchdog Timeout | Process sleep: `sleep 100` | Watchdog Monitor | Killed after configured timeout (e.g. 2s) |
| **SEC-56** | Child Persistence | Child spawns background child: `(sleep 100 &)` | Process Group (`os.killpg`) | Process group terminated, child reaped |
| **SEC-57** | Grandchild Persistence | Parent -> child -> grandchild sleep chain | Process Group (`os.killpg`) | Entire process tree terminated |
| **SEC-58** | Process Group Detach | Child ignores `SIGTERM` | Escalation Protocol | Terminated unconditionally via `SIGKILL` |
| **SEC-59** | PID Reuse Defense | Delayed cancel after process exited | Ownership & Stat Check | Pre-signal check detects exit; no kill |
| **SEC-60** | Unrelated Process Kill | Cancel request targeting foreign PID | Execution Registry | `TacpSecurityError(NOT_OWNED)` |
| **SEC-61** | Approval Replay | Replaying used approval token | Approval Engine | `TacpSecurityError(APPROVAL_ALREADY_USED)` |
| **SEC-62** | Parameter Tampering | Altering argv after approval granted | Execution Service | Contract hash mismatch -> `NOT_AUTHORIZED` |
| **SEC-63** | Parameter Tampering | Altering cwd after approval granted | Execution Service | Contract hash mismatch -> `NOT_AUTHORIZED` |
| **SEC-64** | Parameter Tampering | Altering environment after approval | Execution Service | Contract hash mismatch -> `NOT_AUTHORIZED` |
| **SEC-65** | Parameter Tampering | Altering timeout after approval | Execution Service | Contract hash mismatch -> `NOT_AUTHORIZED` |
| **SEC-66** | Parameter Tampering | Altering network_enabled after approval | Execution Service | Contract hash mismatch -> `NOT_AUTHORIZED` |
| **SEC-67** | Expired Approval | Submitting expired approval ticket | Approval Engine | `TacpSecurityError(APPROVAL_EXPIRED)` |
| **SEC-68** | Principal Mismatch | Agent B using approval issued to Agent A | Approval Engine | `TacpSecurityError(PRINCIPAL_MISMATCH)` |
| **SEC-69** | Workspace Mismatch | Ticket issued for WS1 used in WS2 | Approval Engine | `TacpSecurityError(WORKSPACE_MISMATCH)` |
| **SEC-70** | Capability Mismatch | Ticket for `fs.read` used in `execution` | Approval Engine | `TacpSecurityError(CAPABILITY_MISMATCH)` |
| **SEC-71** | Forged Token | Random bearer token submitted | Approval Engine | `TacpNotFoundError(TICKET_NOT_FOUND)` |
| **SEC-72** | Approval Concurrency | Race: simultaneous consume of same ticket | Approval Engine (`BEGIN IMMEDIATE`) | Exactly one succeeds; other gets `ALREADY_USED` |
| **SEC-73** | Approval Concurrency | Race: approve vs revoke | Approval Engine (`WHERE status='PENDING'`) | Atomic transition; no corrupt state |
| **SEC-74** | Approval Concurrency | Race: approve vs expire | Approval Engine (`WHERE status='PENDING'`) | Atomic transition; no corrupt state |
| **SEC-75** | Policy Fail-Closed | Unknown capability submitted | Policy Engine | `TacpSecurityError(NOT_AUTHORIZED)` |
| **SEC-76** | Executable Whitelist | Non-whitelisted executable: `gcc` | Policy / Resolver | `TacpSecurityError(EXECUTABLE_NOT_PERMITTED)` |
| **SEC-77** | Executable Whitelist | Non-whitelisted executable: `apt` | Policy / Resolver | `TacpSecurityError(EXECUTABLE_NOT_PERMITTED)` |
| **SEC-78** | Executable Whitelist | Package manager: `pkg install` | Policy / Resolver | `TacpSecurityError(EXECUTABLE_NOT_PERMITTED)` |
| **SEC-79** | Executable Whitelist | Package manager: `pip install` | Policy / Resolver | `TacpSecurityError(EXECUTABLE_NOT_PERMITTED)` |
| **SEC-80** | Executable Whitelist | Package manager: `npm install` | Policy / Resolver | `TacpSecurityError(EXECUTABLE_NOT_PERMITTED)` |
| **SEC-81** | Executable Whitelist | Destructive utility: `rm -rf` | Policy / Resolver | `TacpSecurityError(EXECUTABLE_NOT_PERMITTED)` |
| **SEC-82** | Executable Whitelist | Destructive utility: `dd` | Policy / Resolver | `TacpSecurityError(EXECUTABLE_NOT_PERMITTED)` |
| **SEC-83** | Executable Whitelist | Destructive utility: `chmod 777` | Policy / Resolver | `TacpSecurityError(EXECUTABLE_NOT_PERMITTED)` |
| **SEC-84** | Executable Whitelist | Destructive utility: `kill -9` | Policy / Resolver | `TacpSecurityError(EXECUTABLE_NOT_PERMITTED)` |
| **SEC-85** | Git Abuse | Git hook execution attempt | Policy / Env | Git helper variables stripped |
| **SEC-86** | Git Abuse | `GIT_SSH_COMMAND` injection | Environment Assembler | Variable unconditionally stripped |
| **SEC-87** | Network Request | Requesting `network_enabled=True` | Policy Engine | `TacpSecurityError(POLICY_DENIED)` |
| **SEC-88** | Network Request | Executable `curl` requested | Policy / Resolver | Rejected: Network utility forbidden |
| **SEC-89** | Network Request | Executable `wget` requested | Policy / Resolver | Rejected: Network utility forbidden |
| **SEC-90** | Network Request | Executable `nc` requested | Policy / Resolver | Rejected: Network utility forbidden |
| **SEC-91** | Terminal Injection | Output containing ANSI escape `\x1b[2J` | Output Sanitizer | Sanitized / stripped from model output |
| **SEC-92** | Terminal Injection | Output containing terminal title escape | Output Sanitizer | Sanitized / stripped from model output |
| **SEC-93** | Terminal Injection | Output containing carriage return `\r` overwrite | Output Sanitizer | Normalized to newline `\n` |
| **SEC-94** | Terminal Injection | Output containing null bytes `\x00` | Output Sanitizer | Replaced with safe placeholder |
| **SEC-95** | Vector Oversize | Argv count > 64 elements | Input Validator | `TacpValidationError(ARGV_TOO_LONG)` |
| **SEC-96** | Argument Oversize | Single argument > 4096 bytes | Input Validator | `TacpValidationError(ARG_TOO_LARGE)` |
| **SEC-97** | Env Oversize | Environment variable count > 16 | Input Validator | `TacpValidationError(ENV_TOO_LARGE)` |
| **SEC-98** | Dry-Run Invariant | `dry_run=True` with malicious command | Execution Service | Returns inspection; NO process spawned |
| **SEC-99** | Audit Concurrency | Concurrent writers appending audit logs | Audit Service (`BEGIN IMMEDIATE`) | Valid linear hash chain verified |
| **SEC-100** | Audit Tampering | Database entry tampered externally | Audit Service (`verify_integrity`) | Detected: Hash chain broken |
| **SEC-101** | Feature Flag Check | `execution_enabled=False` execution request | Policy Engine | `TacpSecurityError(POLICY_DENIED)` |
| **SEC-102** | Restart Recovery | Stale RUNNING process found on boot | Execution Service (Reconciliation) | Reconciles PID/stat; marks ORPHANED/TERMINATED |

---

## 3. Implementation Verification Status

All 102 attack scenarios are formalized in `tests/security/test_execution_security.py`. Every test must execute deterministically and assert that TACP fails closed with explicit error codes and tamper-evident audit logging.
