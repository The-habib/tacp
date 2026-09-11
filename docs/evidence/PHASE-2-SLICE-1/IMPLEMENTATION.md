# Phase 2 — Vertical Slice 1: Implementation Report
**Slice:** `workspace.patch` (Governed Workspace Patch)  
**TACP Version:** `0.2.0-rc.1`  
**Target Platform:** Termux on Android (Linux kernel / aarch64)

---

## 1. Executive Summary

Vertical Slice 1 implements the first governed mutating capability of the Termux AI Control Plane: `workspace.patch`.
In accordance with the constitutional mandate:
> *"AI may be autonomous, but AI must never be sovereign."*

Direct mutation of the filesystem by MCP clients or autonomous agents is forbidden. Every patch operation is strictly governed by a 16-stage pipeline.

---

## 2. 16-Stage Pipeline Mapping

| Stage | Name | Component / Class | Method / Action |
| :--- | :--- | :--- | :--- |
| **1** | MCP Request Protocol | `tacp.access.mcp.server.McpServer` | Decodes JSON-RPC 2.0 `tools/call` for `workspace.patch` |
| **2** | App Service Routing | `tacp.access.mcp.tools.ToolRegistry` | Validates arguments; binds `RequestContext` |
| **3** | Identity & Auth | `tacp.control.identity.IdentityEngine` | Resolves principal identity (`mcp-client`, `human`) |
| **4** | Capability Discovery | `tacp.core.capability_service.CapabilityService` | Checks registered capability definition and input schema |
| **5** | Resource Resolution | `tacp.core.workspace_service.WorkspaceService` | Resolves `workspace_id`, checks workspace active status |
| **6** | Validation & Jail Guard | `tacp.providers.filesystem.FilesystemProvider` | Enforces path jail, rejects traversal, raw symlinks, binary, null bytes, and size limits |
| **7** | Policy Enforcement | `tacp.control.policy.PolicyEngine` | Checks mutation enabled flag, rejects protected paths (`.git`, `.tacp`, keys), enforces dry-run or approval |
| **8** | Risk Evaluation | `tacp.control.risk.RiskEvaluator` | Classifies action: `R1` (dry-run simulation) or `R2` (live mutation) |
| **9** | Budget & Limits | `tacp.infrastructure.config.OutputLimits` | Checks diff length, file size, resulting size bounds |
| **10** | Concurrency Lock | `tacp.core.lock_service.LockService` | Single-resource lock (`{ws_id}:{subpath}`) with 30s TTL |
| **11** | Human Approval | `tacp.control.approval.ApprovalEngine` | Verifies single-use token, matching 5D criteria (principal, action, ws, target, diff_hash) |
| **12** | Execution Contract | `tacp.domain.contract.ExecutionContract` | Issues formal immutable execution contract before mutation |
| **13** | Atomic Provider Execution | `tacp.providers.filesystem.FilesystemProvider` | In-memory unified diff hunk patch, pre-mutation snapshot, same-dir `.tacp_tmp_*` atomic replace with `fsync` |
| **14** | Observation & Verification | `tacp.providers.filesystem.FilesystemProvider` | Verifies resulting file on disk, confirms expected checksum |
| **15** | Sanitization | `tacp.infrastructure.logging.redact_string` | Sanitizes diff snippets and error strings for sensitive credentials |
| **16** | Audit Trail & Persistence | `tacp.core.audit_service.AuditService` | Persists audit record and patch record into SQLite database |

---

## 3. Core Component Architecture

### 3.1 Domain Models
- `WorkspacePatch`: Represents patch entity with status, before/after checksums, diff content, and metrics.
- `PatchResult`: Result payload returned to caller containing patch id, status, lines added/removed, resulting size, and checksum.
- `ExecutionContract`: Formal bounded contract issued for mutating operations with expiry, scope, and snapshot references.

### 3.2 Concurrency & Collision Prevention
- **Optimistic Concurrency Control (OCC)**: Caller must provide `base_checksum` (SHA-256). If disk content does not match, operation aborts with `CONFLICT` without modifying disk state.
- **Pessimistic Resource Locking**: `LockService` prevents concurrent in-flight mutations to the same file.
- **Android Atomic File Replacement**: Replaces target using a temporary file (`.tacp_tmp_{uuid}`) located in the **same parent directory** followed by `os.fsync` and POSIX `os.replace`. This avoids Android `EXDEV` (cross-device link) errors that occur when using global `/tmp`.

### 3.3 Snapshots & Rollback
- Prior to any live mutation, a complete copy of the original file is archived at `~/.tacp/snapshots/{patch_id}/{filename}`.
- `rollback_patch(patch_id)` restores the snapshot with OCC checks ensuring the file has not been modified out-of-band since the patch.
