# TACP Secret Brokerage & Protection Model

**Document:** `docs/security/SECRET-MODEL.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**Security Lead:** Antigravity Principal Security Engineer  
**Date:** September 11, 2026  

---

## 1. Secret Protection Principles

1. **Zero Secret Visibility in Model Context**: AI agents must never be able to read, browse, or query plaintext secrets (API keys, private tokens, passwords, private keys) through ordinary filesystem inspection tools.
2. **Internal Injection Only**: When a child process (such as a build tool, git push, or test runner) requires a credential, the secret is retrieved internally by TACP's `SecretBroker` and injected directly into the spawned process environment or secure pipe.
3. **Scrubbing in Depth**: All text leaving child processes, logs, audit trails, error messages, and tool responses passes through multi-pattern regex redaction filters before being delivered to the agent context or written to disk.
4. **Minimal Surface Area**: TACP does not build a sprawling credential manager in Phase 2. It restricts secret handling strictly to necessary execution injection and redaction.

---

## 2. Protected Secret Categories & Patterns

The platform identifies and protects four categories of secrets:

| Category | File Patterns & Identifiers | Injection Target | Redaction Replacement |
|---|---|---|---|
| **API Keys & Bearer Tokens** | `sk-[a-zA-Z0-9]{20,}`, `ghp_[a-zA-Z0-9]{36}`, `xox[baprs]-[a-zA-Z0-9]{10,}` | Child process env (e.g. `OPENAI_API_KEY`) | `[REDACTED_API_KEY]` |
| **Private Keys & Certificates** | `id_rsa`, `id_ed25519`, `*.pem`, `*.key`, `-----BEGIN * PRIVATE KEY-----` | SSH agent pipe / memory | `[REDACTED_PRIVATE_KEY]` |
| **Environment & Config Files** | `.env`, `.env.*`, `credentials.json`, `auth.json` | Parsed internally into key-value map | Blocked from `fs.read` |
| **History & Private Telemetry**| `.bash_history`, `.zsh_history`, `~/.tacp/auth.token` | None (Forbidden) | Blocked from `fs.read` |

---

## 3. Secret Brokerage Architecture

```
[Agent Requests Command / Job]
           │
           │  (Declares required credential key: e.g. "needs: GITHUB_TOKEN")
           v
[Control Plane Policy Check]
           │
           ├── Asserts principal is authorized for secret injection
           ├── Asserts target command is on safe allowlist
           v
[SecretBroker (Internal)]
           │
           ├── Retrieves secret value from secure storage (~/.tacp/secrets.db, mode 0600)
           ├── Creates isolated process environment dictionary: env["GITHUB_TOKEN"] = val
           v
[Child Process Spawned]
           │  (Child receives environment directly in Linux memory)
           v
[Output Sanitizer Filter]
           │  (Scans stdout/stderr for secret value; replaces with [REDACTED])
           v
[Response Delivered to Model]
           (Model receives sanitized output with ZERO plaintext credentials)
```

---

## 4. Multi-Layer Redaction Filter

TACP maintains an active redaction engine in `src/tacp/infrastructure/logging.py` executed across 4 inspection gates:

1. **Gate 1: Pre-Read Filter (`fs.read`)**:
   Files matching secret extensions (`.env`, `.key`, `.pem`) or secret names (`id_rsa`, `credentials.json`) are blocked before disk reads occur, returning `ErrorCode.SECRET_PROTECTED`.
2. **Gate 2: Content Scanner (`read_file`, `search_files`)**:
   All read contents and search match snippets are scanned with regex patterns for known API token prefixes (`sk-`, `ghp_`, `bearer `, `BEGIN PRIVATE KEY`). Matched spans are replaced with `[REDACTED]`.
3. **Gate 3: Parameter Sanitizer (`tools.py`)**:
   Tool invocation arguments recorded in `AuditEvent` records are sanitized via `redact_dict(args)` so API keys passed in parameters are never logged to SQLite or disk.
4. **Gate 4: Output Stream Sanitizer (Command Output)**:
   Child process stdout and stderr streams are buffered through line-by-line regex sanitizers before formatting into JSON-RPC response payloads.

---

## 5. Security & Safety Invariants

1. **No Secret Mutation via Workspace Patch**: `workspace.patch` cannot target or create files classified as `SECRET` (e.g. `.env`, `id_rsa`). Attempts fail closed with `ErrorCode.SECRET_PROTECTED`.
2. **Database Protection**: The secret store is held in SQLite protected by POSIX permissions `0600` owned by `u0_a316`, located in `~/.tacp/private/`.
3. **Audit Log Hygiene**: Storing plaintext secrets in the audit log is considered an **SEV-1 security defect**. The audit schema strictly stores `parameters_redacted`.
