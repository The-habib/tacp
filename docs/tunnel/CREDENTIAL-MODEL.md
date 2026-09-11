# Credential & Authentication Model

## 1. Principles of Credential Segregation
The integration with OpenAI Secure MCP Tunnel strictly separates administrative provisioning privileges from runtime execution credentials:

```
+-----------------------------------------------------------------------------+
|                          OPENAI_ADMIN_KEY                                   |
| - Scope: Creation, deletion, and configuration of tunnels.                  |
| - Location: Developer environment / interactive shell during setup ONLY.    |
| - Invariant: NEVER provided to `tunnel-client run` or persistent daemons.   |
+-----------------------------------------------------------------------------+
                                       |
                     (Used only during provisioning)
                                       v
+-----------------------------------------------------------------------------+
|                       CONTROL_PLANE_TUNNEL_ID                               |
| - Scope: Public identifier for the established tunnel.                      |
| - Safety: Non-secret; safe for reference in status checks.                  |
+-----------------------------------------------------------------------------+
                                       +
+-----------------------------------------------------------------------------+
|                       CONTROL_PLANE_API_KEY                                 |
| - Scope: Runtime authentication between local `tunnel-client` and OpenAI.   |
| - Location: `env:CONTROL_PLANE_API_KEY`.                                    |
| - Handling: Ephemeral; strictly masked in all logs, status, and reports.    |
+-----------------------------------------------------------------------------+
```

## 2. Zero Leakage Invariant
1. **CLI Commands**:
   * `tacp remote status` reports credential state as `CONFIGURED (hidden)` or `NOT CONFIGURED`. It never prints key characters beyond safe prefix indicators.
   * `tacp doctor` masks tunnel IDs (`tun_123456...`) and verifies API key presence without echoing values.
2. **Audit Logs**:
   * All audit parameters pass through `redact_dict` / `redact_string`. Any string matching secret regexes (`sk-...`, `ghp_...`, `-----BEGIN PRIVATE KEY-----`) is replaced with `[REDACTED_SECRET]`.
3. **Database Security**:
   * API keys and tokens are never stored in the TACP SQLite database. The database stores only audit trails, workspace metadata, and lock records.
4. **Git Repository Hygiene**:
   * Tracked repository files are guarded by automated regression checks (`test_no_secrets_in_repository_files`). No `.env` or credential files are ever committed.
