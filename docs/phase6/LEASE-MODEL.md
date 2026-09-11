# TACP Phase 6: Bounded Capability Lease Model
**Document ID:** `TACP-LEASE-001`  
**Classification:** Security & Authorization Specification  
**Release Target:** v0.5.0-alpha / Phase 6  
**Date:** September 2026  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Executive Summary

In long-running development sessions, an AI agent may execute dozens of small, interrelated edits within a single project. Requiring human approval on every individual file write disrupts concentration and induces approval fatigue. Conversely, granting broad "unrestricted permission" compromises the foundational principle of least privilege.

The **Bounded Capability Lease Model** solves this by granting time-bounded, resource-bounded, and risk-capped authorization tickets that allow friction-free execution within an explicitly approved scope.

---

## 2. Capability Lease Schema

A capability lease is an immutable, cryptographically tracked record stored in SQLite table `leases`:

```json
{
  "lease_id": "lease-8f3a1b02",
  "principal_id": "local-agent-01",
  "workspace_id": "ws-tacp-dev",
  "capabilities": ["workspace.patch", "workspace.patch_batch"],
  "resources": ["src/**", "tests/**"],
  "risk_ceiling": "R2",
  "budget": 20,
  "budget_remaining": 17,
  "issued_at": "2026-09-11T10:00:00Z",
  "expires_at": "2026-09-11T10:30:00Z",
  "trust_profile": "BALANCED",
  "policy_version": 1,
  "session_id": "sess-410a8",
  "revoked": false
}
```

### Attribute Specifications:
- **`lease_id`:** Unique alphanumeric token used as authentication credential.
- **`principal_id`:** Identity of the agent or client holding the lease. Cannot be transferred.
- **`workspace_id`:** Strict jail. The lease is invalid if evaluated against any other workspace.
- **`capabilities`:** Whitelist of allowed action types. An $R_2$ patch lease CANNOT execute $R_3$ `execution.request`.
- **`resources`:** Glob patterns or path lists restricting where modifications can occur.
- **`risk_ceiling`:** Absolute maximum risk level permitted. If a requested operation evaluates to $R_3$, the lease is bypassed.
- **`budget_remaining`:** Decremented atomically upon each successful operation. When it reaches 0, the lease expires.
- **`expires_at`:** Hard time limit (maximum 60 minutes).
- **`revoked`:** Boolean flag set to `true` on manual revocation or emergency stop.

---

## 3. Lease Lifecycle State Machine

```
               ┌─────────────┐
               │   ISSUED    │
               └──────┬──────┘
                      │ (Atomic decrement on use)
                      ▼
               ┌─────────────┐
        ┌─────►│   ACTIVE    ├──────┐
        │      └──────┬──────┘      │
        │ (Within     │             │
        │  Budget)    │ (Budget=0   │ (now > expires_at)
        │             │  or Revoke) │
        └─────────────┼─────────────┼──────────────┐
                      ▼             ▼              ▼
               ┌─────────────┐┌───────────┐┌───────────────┐
               │  EXHAUSTED  ││  EXPIRED  ││    REVOKED    │
               └─────────────┘└───────────┘└───────────────┘
```

### Atomic Consumption SQL:
To prevent race conditions during concurrent tool calls, budget decrement is performed atomically in SQLite:
```sql
UPDATE leases
SET budget_remaining = budget_remaining - 1
WHERE lease_id = ?
  AND principal_id = ?
  AND workspace_id = ?
  AND revoked = 0
  AND budget_remaining > 0
  AND expires_at > datetime('now');
```

---

## 4. Lease Verification Invariants

When an agent presents a `lease_id`, TACP verifies all 8 boundary conditions:
1. **Principal Match:** `lease.principal_id == request.principal.id`
2. **Workspace Match:** `lease.workspace_id == request.workspace_id`
3. **Capability Match:** `request.capability in lease.capabilities`
4. **Risk Ceiling:** `request.risk_level <= lease.risk_ceiling`
5. **Resource Jail:** `request.target_path` matches `lease.resources`
6. **Time Validity:** `datetime.now(utc) < lease.expires_at`
7. **Budget Validity:** `lease.budget_remaining > 0`
8. **Revocation Check:** `lease.revoked == false`

If ANY check fails, TACP automatically falls back to `REQUIRE_APPROVAL` (or `DENY` if under `LOCKDOWN`).

---

## 5. Revocation & Emergency Controls

Leases can be revoked instantly:
1. **Explicit Revocation:** `tacp lease revoke <lease_id>`
2. **Trust Profile Transition:** Changing the trust profile (e.g. from `BALANCED` to `LOCKDOWN` or `STRICT`) immediately marks all active leases as `revoked = true`.
3. **Emergency Stop:** `tacp emergency-stop` kills running processes AND revokes all active leases across all workspaces.
