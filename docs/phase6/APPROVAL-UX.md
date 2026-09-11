# TACP Phase 6: Plan-First UX & Approval Grouping Specification
**Document ID:** `TACP-UX-APPR-001`  
**Classification:** Product Architecture & User Experience Design  
**Release Target:** v0.5.0-alpha / Phase 6  
**Date:** September 2026  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. The Problem of Approval Fatigue

Approval fatigue is a primary vulnerability in agentic control planes:
- When an AI agent submits 10 separate file changes, showing 10 successive approval prompts forces the user to blindly click "Approve" without reading the code.
- Conversely, dumping a 2,000-line raw diff overwhelms the user with technical noise.

TACP Phase 6 solves this by enforcing a **Plan-First, Grouped-Approval UX**.

---

## 2. Plan-First Architecture

Before performing any mutating ($R_2$) or executing ($R_3$) action that requires human oversight, TACP encourages or mandates the **Dry-Run Plan Protocol**:

```
1. AI generates action with dry_run = true
2. TACP validates bounds, parses diffs/args, resolves paths
3. TACP returns a Concise Operation Plan (No side effects)
4. Human reviews the Plan (One comprehensive decision)
5. Human approves Plan -> issues Grouped Approval Ticket
6. AI executes live action with approval_token
```

### 2.1 Mutation Plan Schema (`workspace.patch` / `patch_batch`)
Instead of flooding the terminal with raw diff text, the dry-run response returns a structured plan:

```json
{
  "status": "DRY_RUN",
  "plan_hash": "sha256-e9c402...",
  "risk_level": "R2",
  "workspace_id": "ws-tacp-dev",
  "summary": {
    "files_affected": 3,
    "lines_added": 24,
    "lines_removed": 8,
    "total_byte_delta": 412,
    "rollback_ready": true
  },
  "files": [
    {"path": "src/auth.py", "action": "MODIFY", "lines_added": 12, "lines_removed": 2},
    {"path": "tests/test_auth.py", "action": "MODIFY", "lines_added": 12, "lines_removed": 6},
    {"path": "docs/auth.md", "action": "CREATE", "lines_added": 0, "lines_removed": 0}
  ],
  "approval_required": true,
  "action_type": "workspace.patch_batch"
}
```

### 2.2 Execution Plan Schema (`execution.request`)
For process execution, dry-run mode reveals all resolved environment and process boundaries:

```json
{
  "status": "DRY_RUN",
  "plan_hash": "sha256-3b1a8f...",
  "risk_level": "R3",
  "workspace_id": "ws-tacp-dev",
  "executable": "printf",
  "resolved_executable": "/system/bin/printf",
  "binary_digest": "sha256-a78b40...",
  "argv": ["printf", "%s\n", "Testing deployment status"],
  "cwd": "/data/data/com.termux/files/home/projects/tacp",
  "network_policy": "NETWORK_UNENFORCED",
  "timeout_seconds": 10,
  "max_stdout_bytes": 1024,
  "approval_required": true,
  "process_spawned": false
}
```

---

## 3. Approval Grouping (`ApprovalGroup`)

To prevent multi-prompt friction, TACP Phase 6 introduces **Grouped Approvals**:
- A single approval ticket can authorize an entire bounded set of operations belonging to a verified plan.
- The ticket is cryptographically bound to the canonical `plan_hash`.
- If the AI alters a single file path, adds an extra file, increases the line delta, or changes the executable argv, the `plan_hash` changes, and the approval ticket is immediately rejected.

### Safety Invariants of Grouped Approvals:
1. **Zero Open-Ended Approval:** An approval ticket CANNOT be granted for "all future operations."
2. **Strict Time Limits:** Grouped tickets expire after 15 minutes by default.
3. **Single-Use Consumption:** Once the approved batch is committed, the ticket is marked `CONSUMED` and cannot be replayed.

---

## 4. Human Approval Interface Guidelines

When presenting an approval prompt to the user (via CLI or IDE modal), TACP formats the decision card using the **9 Core Elements**:

```
╔══════════════════════════════════════════════════════════════════════╗
║                    TACP APPROVAL REQUIRED [R2]                       ║
╠══════════════════════════════════════════════════════════════════════╣
║ WHAT:     Batch patch 3 files in workspace 'tacp-dev'                ║
║ WHERE:    /data/data/com.termux/files/home/projects/tacp             ║
║ WHY:      Fix authentication token expiration handling               ║
║ RISK:     R2 (Bounded reversible workspace mutation)                 ║
║ SIZE:     3 files | +24 lines | -8 lines (~412 bytes)                ║
║ DURATION: Instantaneous (Atomic replace)                             ║
║ NETWORK:  None (Offline execution)                                   ║
║ ROLLBACK: Guaranteed (Pre-image snapshot will be captured)           ║
║ EXPIRES:  15 minutes                                                 ║
╠══════════════════════════════════════════════════════════════════════╣
║ [A] Approve Plan    [D] View Detailed Diff    [R] Reject Action      ║
╚══════════════════════════════════════════════════════════════════════╝
```

By displaying exact human-readable metadata, the user evaluates **intent and impact** rather than being trained to blindly approve.
