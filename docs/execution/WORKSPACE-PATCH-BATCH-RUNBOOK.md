# TACP RUNBOOK: GOVERNED WORKSPACE PATCH BATCH (`workspace.patch_batch`)

## 1. Overview & Architectural Principles

TACP (*Termux AI Control Plane*) enforces the constitutional principle:
> **"AI MAY BE AUTONOMOUS, BUT AI MUST NEVER BE SOVEREIGN."**

`workspace.patch_batch` is the second governed mutating capability in TACP. It provides atomic, all-or-nothing multi-file text patch modifications to existing files within an authorized workspace using unified diff format.

Every multi-file patch batch must strictly traverse the **16-stage pipeline**:

```
MCP Request / CLI Command
  ↓
App Service / Dispatcher
  ↓
Identity Verification
  ↓
Capability Check (workspace.patch_batch)
  ↓
Resource & Target Resolution
  ↓
Input Validation & Duplicate Target Denial
  ↓
Policy Engine (Dual Feature Flags & Path Security)
  ↓
Risk Evaluation (CRITICAL multi-target risk)
  ↓
Budget / Quota Limits (File count & Byte bounds)
  ↓
Deterministic Multi-Resource Locking (Lexicographical ordering)
  ↓
Approval Verification (Canonical SHA-256 Batch Hash)
  ↓
Execution Contract Formulation
  ↓
Filesystem Provider (Atomic Staging + fsync + os.replace)
  ↓
Observation / Post-Write Checksum Verification
  ↓
Sanitization & Audit Trail Hashing
  ↓
Result Response (Full batch manifest & IDs)
```

---

## 2. Configuration & Dual Feature Flags

### 2.1 Default State: Strict Denial
By default, TACP operates in strict **read-only** mode:
- `mutation_enabled = false`
- `batch_mutation_enabled = false`

In this mode:
- The MCP tool `workspace.patch_batch` is not exposed in `tools/list`.
- Direct invocations return `POLICY_DENIED`.

### 2.2 Enabling Batch Mutations
Multi-file batch mutation requires **both** flags to be enabled:
```bash
# Environment variables:
export TACP_MUTATION_ENABLED=1
export TACP_BATCH_MUTATION_ENABLED=1

# Or CLI flags when launching stdio server:
tacp serve --allow-mutation --allow-batch-mutation
```
*Note: If `TACP_MUTATION_ENABLED=0` and `TACP_BATCH_MUTATION_ENABLED=1`, batch mutation remains strictly disabled.*

---

## 3. Resource Limits & Guardrails

| Parameter | Default Limit | Description |
| :--- | :--- | :--- |
| `max_batch_files` | 10 | Maximum number of files in a single batch |
| `max_batch_patch_total_bytes` | 1,048,576 (1 MB) | Maximum cumulative patch diff size across all items |
| `max_batch_resulting_total_bytes` | 5,242,880 (5 MB) | Maximum cumulative resulting file size across all items |
| `max_patch_bytes` | 262,144 (256 KB) | Maximum patch diff size per file |
| `max_file_size_bytes` | 1,048,576 (1 MB) | Maximum initial size per file |
| `max_resulting_file_bytes` | 2,097,152 (2 MB) | Maximum resulting size per file |

---

## 4. Operational Workflow

### 4.1 Dry-Run Simulation (No Approval Required)
Callers should always validate a multi-file patch batch with `dry_run = true`:
```bash
node /data/data/com.termux/files/usr/bin/mcp-inspector --cli \
  --server tacp_batch \
  --method tools/call \
  --tool-name workspace.patch_batch \
  --tool-args-json \x27{
    "workspace_id": "<WORKSPACE_ID>",
    "dry_run": true,
    "patches": [
      {
        "subpath": "src/module_a.py",
        "patch_content": "--- a\n+++ a\n...",
        "base_checksum": "<SHA256_A>"
      },
      {
        "subpath": "src/module_b.py",
        "patch_content": "--- a\n+++ a\n...",
        "base_checksum": "<SHA256_B>"
      }
    ]
  }\x27
```

### 4.2 Live Execution & Human Approval Ticket Generation
When executing with `dry_run = false` without an approval token, TACP generates an approval ticket:
```json
{
  "isError": true,
  "content": [
    {
      "type": "text",
      "text": "Error (APPROVAL_REQUIRED): Execution of \x27workspace.patch_batch\x27 requires explicit human approval. Ticket created: tacp_appr_... (id: appr-...)"
    }
  ]
}
```

The operator inspects the ticket and canonical batch hash:
```python
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database
from tacp.control.approval import ApprovalEngine

cfg = TacpConfig.load()
db = Database(cfg.db_path)
db.connect()
ae = ApprovalEngine(db)
ticket = ae.approve("tacp_appr_...")
```

### 4.3 Applying the Approved Batch
Re-invoke `workspace.patch_batch` with `approval_token`:
```bash
node /data/data/com.termux/files/usr/bin/mcp-inspector --cli \
  --server tacp_batch \
  --method tools/call \
  --tool-name workspace.patch_batch \
  --tool-args-json \x27{
    "workspace_id": "<WORKSPACE_ID>",
    "dry_run": false,
    "approval_token": "tacp_appr_...",
    "patches": [...]
  }\x27
```

---

## 5. Inspection, Audit & Rollback Procedures

### 5.1 Listing Batches
```bash
tacp batch list
```

### 5.2 Showing Batch Details
```bash
tacp batch show batch-20b74673
```

### 5.3 Emergency Rollback
Every batch execution saves snapshots for each modified file to `~/.tacp/snapshots/<batch_id>/`.
To roll back all files to their pre-batch contents:
```bash
tacp batch rollback batch-20b74673
```
TACP restores all files atomically and records the rollback event in the tamper-evident audit log.
