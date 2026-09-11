# Evidence: Remote Audit Logging & Verification

## Event Schema Validation
Every remote MCP call is immutably recorded in SQLite `audit_logs` table with:
* `principal`: `chatgpt-session-...` (tagged with remote identity)
* `policy_decision`: `ALLOWED` or `DENY`
* `result`: `SUCCESS` or `ERROR: ...`
* `parameters_redacted`: JSON string with all tokens and secrets redacted
* `prev_hash`: SHA-256 hash of prior event
* `entry_hash`: SHA-256 hash of current canonical payload

## Hash Chain Integrity Verification
* **Tool**: `AuditService.verify_integrity()`
* **Verification Status**: `True` (Valid)
* **Broken Links**: `0`
* **Tamper Evidence**: Any modification to historical audit records invalidates subsequent hashes.
