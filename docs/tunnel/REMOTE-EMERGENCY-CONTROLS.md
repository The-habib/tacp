# Remote Emergency Controls & Incident Response

## 1. Design Philosophy
Emergency controls must be completely independent of the remote agent. If ChatGPT, OpenAI network infrastructure, or the tunnel daemon misbehaves, the local operator retains 100% sovereign authority to immediately sever connectivity and halt operations without requiring remote acknowledgment.

## 2. Emergency Kill Switches

### A. Immediate Process Severance (Hard Kill)
To instantly kill the outbound tunnel process:
```bash
# Terminate the tunnel-client process immediately
pkill -9 -f tunnel-client
```
* **Effect**: Terminate the outbound TLS connection immediately. ChatGPT's connector will experience an instant disconnection (connection reset).
* **Side-effects**: None on local state. TACP stdio server and SQLite WAL database remain completely intact.

### B. Policy-Level Emergency Stop (Configuration Kill Switch)
If the operator wishes to disable remote access while keeping local CLI services running:
```bash
export TACP_REMOTE_ENABLED=false
```
* **Effect**: The `PolicyEngine` enters fail-closed lockdown for all remote requests. Any incoming call associated with `PrincipalType.REMOTE_AI` will be rejected immediately with:
  ```
  Access denied: Remote access is disabled in TACP configuration
  ```

### C. Emergency Lockdown Trust Profile
To enforce total lockdown across both local and remote operations:
```bash
export TACP_TRUST_PROFILE=LOCKDOWN
```
* **Effect**: All mutating and executing capabilities are disabled across all principals. Remote AI requests receive zero mutation/execution authority.

## 3. Disconnect and Recovery Invariants
* **Database Resiliency**: TACP uses SQLite in WAL (Write-Ahead Logging) mode with `NORMAL` synchronous commits. Abrupt tunnel disconnection cannot corrupt the database schema or active transactions.
* **Audit Chain Continuity**: Every request handled prior to termination is hashed with SHA-256 and chained to `prev_hash`. Upon reconnection, subsequent events attach seamlessly to the latest hash block with zero broken links.
