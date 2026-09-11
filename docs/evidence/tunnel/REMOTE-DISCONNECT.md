# Evidence: Remote Disconnect Handling & Resilience

## Abrupt Disconnection Simulation
1. **Scenario**: `tunnel-client` experiences sudden network failure or SIGKILL termination while handling client requests.
2. **Behavior**:
   * TACP stdio pipe encounters EOF on stdin.
   * `McpServer` loop cleanly terminates or waits for new session depending on daemon manager.
   * Active database connections close cleanly.
   * Uncommitted or aborted requests leave zero dangling locks or partial files.
3. **Database Health**:
   * SQLite WAL ensures write-ahead log files are either committed or rolled back automatically on reopen.
   * `PRAGMA integrity_check` returns `ok`.

## Test Validation
Verified in `tests/integration/test_remote_tunnel.py::test_audit_hash_chain_and_restart_resilience`.
