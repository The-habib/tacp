# TACP RUNBOOK: GOVERNED WORKSPACE PATCH (`workspace.patch`)

## 1. Overview & Architectural Principles

TACP (*Termux AI Control Plane*) enforces the constitutional principle:
> **"AI MAY BE AUTONOMOUS, BUT AI MUST NEVER BE SOVEREIGN."**

`workspace.patch` is the first governed mutating capability in TACP. It enables targeted, auditable modifications to existing text files within authorized workspaces using unified diff format.

Direct file mutation from MCP clients or AI agents is strictly prohibited. Every patch must traverse the **16-stage pipeline**:

```
MCP Request
  ↓
App Service
  ↓
Identity
  ↓
Capability Check
  ↓
Resource Resolution
  ↓
Input Validation
  ↓
Policy Engine
  ↓
Risk Evaluation
  ↓
Budget / Quota
  ↓
Lock / Lease
  ↓
Approval Check
  ↓
Execution Contract
  ↓
Filesystem Provider
  ↓
Observation / Verification
  ↓
Sanitization
  ↓
Audit Trail
  ↓
Result Response
```

---

## 2. Configuration & Activation

### 2.1 Default State: Read-Only
By default, TACP operates in strict **read-only** mode (`mutation_enabled = false`). In this mode:
- The MCP tool `workspace.patch` is hidden from the MCP tools list.
- Any attempt to invoke `workspace.patch` results in `POLICY_DENIED`.

### 2.2 Enabling Mutations
To enable mutating capabilities, set the environment variable:
```bash
export TACP_MUTATION_ENABLED=1
```
Or launch the server:
```bash
tacp serve --allow-mutation
```

### 2.3 Resource Limits
Governed patch operations enforce strict bounding limits:
- `max_patch_bytes`: 262,144 bytes (256 KB)
- `max_file_size_bytes`: 1,048,576 bytes (1 MB)
- `max_resulting_file_bytes`: 2,097,152 bytes (2 MB)

---

## 3. Patch Lifecycle Workflows

### 3.1 Stage A: Dry-Run Simulation (No Approval Required)
Agents are required to first test patches using dry-run simulation:

1. **Calculate Base Checksum**:
   Compute the SHA-256 hash of the target file before generating a diff:
   ```bash
   sha256sum src/target.py
   ```
2. **Issue Dry-Run Request**:
   Send MCP tool call `workspace.patch` with `dry_run=true`:
   ```json
   {
     "workspace_id": "ws-1234",
     "subpath": "src/target.py",
     "patch_content": "--- a/src/target.py
+++ b/src/target.py
@@ -1,3 +1,3 @@
 def hello():
-    return 'old'
+    return 'new'
",
     "base_checksum": "a3f5...",
     "dry_run": true
   }
   ```
3. **Inspect Simulation Result**:
   - Status: `SIMULATED`
   - Returns added line count, removed line count, resulting byte size, and predicted post-mutation checksum.
   - Verifies hunk matching and syntactical accuracy without altering disk state.

---

## 3.2 Stage B: Requesting Live Mutation & Approval Ticket Generation

When an agent executes a live mutation (`dry_run=false`) without an approved token:
1. The request traverses the pipeline to **Stage 11 (Approval)**.
2. The `PolicyEngine` and `ApprovalEngine` flag the request as `R2` risk.
3. An `ApprovalTicket` is automatically minted with status `PENDING`.
4. The system raises `TacpApprovalRequiredError`:
   ```
   Execution of 'workspace.patch' requires explicit human approval. Ticket created: appr_9f8a... (id: ticket-abc)
   ```

---

## 3.3 Stage C: Human Review & Approval

The human operator reviews the ticket:
```bash
# List pending approval tickets
tacp approvals list

# Review specific ticket diff and metadata
tacp approvals show appr_9f8a...

# Approve the ticket
tacp approvals approve appr_9f8a... --comment "Approved bugfix"
```

#### Ticket Security Invariants:
- **5-Dimensional Scoping**: The token is cryptographically bound to:
  1. `principal_id` (agent identity)
  2. `action_type` (`workspace.patch`)
  3. `workspace_id`
  4. `target_path`
  5. `patch_hash` (SHA-256 of exact patch content)
- **Single-Use Consumption**: Once consumed by `workspace.patch`, the ticket transitions atomically to `CONSUMED`. Replay attacks fail immediately.
- **TTL Expiration**: Tickets expire after 300 seconds (5 minutes) if unapproved or unused.

---

## 3.4 Stage D: Execution with Approved Token

The agent resubmits the request with the approval token:
```json
{
  "workspace_id": "ws-1234",
  "subpath": "src/target.py",
  "patch_content": "--- a/src/target.py
+++ b/src/target.py
@@ -1,3 +1,3 @@
 def hello():
-    return 'old'
+    return 'new'
",
  "base_checksum": "a3f5...",
  "dry_run": false,
  "approval_token": "appr_9f8a..."
}
```

The system executes:
1. Re-validates jail boundaries, path invariants, and base checksum.
2. Acquires exclusive resource lock: `{workspace_id}:{subpath}`.
3. Consumes approval ticket atomically.
4. Generates an `ExecutionContract`.
5. Creates pre-mutation snapshot in `~/.tacp/snapshots/{patch_id}/target.py`.
6. Creates atomic temp file in same directory: `.tacp_tmp_{uuid}`.
7. Flushes and executes `os.fsync()`.
8. Atomically replaces target via POSIX `os.replace()`.
9. Verifies post-write disk state and checksum.
10. Records audit event and persists patch record in SQLite.
11. Releases resource lock and returns `PatchResult`.

---

## 4. Rollback Workflow

If a patch causes unforeseen application failures, the operator or agent can initiate an immediate rollback.

### 4.1 CLI Rollback
```bash
# Inspect recent patches
tacp patches list

# Rollback specific patch
tacp patches rollback patch-8fa2b1
```

### 4.2 Rollback Safety Invariants
1. **Target Checksum Guard**: Rollback verifies that the target file on disk matches `after_checksum` of the patch being reverted. If concurrent edits have modified the file, rollback fails with `CONFLICT` to prevent silent overwrites.
2. **Atomic Temp Restoration**: The snapshot is restored using the same atomic temp file + `fsync` + `os.replace` flow.
3. **Audit Trail**: Rollback actions are logged to the TACP audit table with status `ROLLED_BACK`.

---

## 5. Troubleshooting & Error Codes

| Error Code | Meaning | Remediation |
| :--- | :--- | :--- |
| `POLICY_DENIED` | Mutation disabled or protected file targeted. | Set `TACP_MUTATION_ENABLED=1`. Verify target is not `.git`, `.tacp`, `.env`, or a key file. |
| `APPROVAL_REQUIRED` | Live patch invoked without approved token. | Check the returned ticket token; approve via CLI or operator UI. |
| `APPROVAL_EXPIRED` | Ticket TTL exceeded 5 minutes. | Generate a new ticket by resubmitting the request. |
| `CONFLICT` | Target file modified since diff was generated (`base_checksum` mismatch). | Re-read target file, regenerate unified diff with latest contents. |
| `OUTSIDE_WORKSPACE` | Path traversal or symlink attempt detected. | Target path must be relative to workspace root and resolve inside the jail. |
| `RESOURCE_LOCKED` | Another patch operation is in progress on the same file. | Wait for lock release (TTL: 30s) or investigate stale lock. |
