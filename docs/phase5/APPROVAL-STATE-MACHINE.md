# TACP Phase 5: Approval State Machine Specification
**Document ID:** `TACP-APPR-FSM-001`  
**Classification:** Control Plane Specification  
**Release Target:** v0.4.0-rc.1 Hardening / Phase 5  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Formal State Machine Definition

The TACP Approval Subsystem enforces a strict, deterministic finite state machine (FSM) over all mutating capabilities (`workspace.patch`, `workspace.patch_batch`, `execution.request`):

```
                       ┌──────────────┐
                       │   PENDING    │
                       └──────┬───────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
   │   APPROVED   │    │    DENIED    │    │   EXPIRED    │
   └──────┬───────┘    └──────────────┘    └──────────────┘
          │ (Atomic
          │  Single-Use)
          ▼
   ┌──────────────┐
   │   CONSUMED   │
   └──────────────┘
          ▲
          │
   (Revocation can target PENDING or APPROVED prior to consumption)
   ┌──────────────┐
   │   REVOKED    │
   └──────────────┘
```

---

## 2. Legal State Transitions

| From State | Action / Event | Target State | Authorized Actor | Atomic SQL Invariant |
| :--- | :--- | :--- | :--- | :--- |
| `PENDING` | `approve()` | `APPROVED` | Privileged Operator / Human | `UPDATE ... WHERE status = 'PENDING'` |
| `PENDING` | `deny()` | `DENIED` | Operator / Human | `UPDATE ... WHERE status IN ('PENDING', 'APPROVED')` |
| `PENDING` | `revoke()` | `REVOKED` | Operator / Human | `UPDATE ... WHERE status IN ('PENDING', 'APPROVED')` |
| `PENDING` | Clock > `expires_at` | `EXPIRED` | Automatic on access | `UPDATE ... WHERE status = 'PENDING'` |
| `APPROVED` | `verify_and_consume()` | `CONSUMED` | Bound Principal | `UPDATE ... WHERE status = 'APPROVED'` |
| `APPROVED` | `deny()` | `DENIED` | Operator / Human | `UPDATE ... WHERE status IN ('PENDING', 'APPROVED')` |
| `APPROVED` | `revoke()` | `REVOKED` | Operator / Human | `UPDATE ... WHERE status IN ('PENDING', 'APPROVED')` |
| `APPROVED` | Clock > `expires_at` | `EXPIRED` | Automatic on access | `UPDATE ... WHERE status = 'APPROVED'` |

### Terminal States
- `CONSUMED`: Immutable terminal state. **A consumed approval can NEVER transition to any other state, nor be re-executed.**
- `DENIED`: Immutable terminal state.
- `REVOKED`: Immutable terminal state.
- `EXPIRED`: Immutable terminal state.

---

## 3. Concurrency Invariants & Proof of Safety

1. **Single Approval Invariant:** If $N$ threads concurrently attempt `approve()`, exactly one thread receives `rowcount == 1`. All other $N-1$ threads fail with `TacpSecurityError(ErrorCode.POLICY_DENIED)`.
2. **Single Consumption Invariant:** If $M$ workers attempt `verify_and_consume()` with the same bearer token, exactly one worker updates the row to `CONSUMED` (`rowcount == 1`). The remaining $M-1$ attempts encounter `rowcount == 0` and are rejected with `TacpSecurityError(ErrorCode.APPROVAL_ALREADY_USED)`.
3. **No Select-Then-Act TOCTOU:** State transitions do not rely on in-memory status checks. The conditional SQL `UPDATE` enforces atomicity at the SQLite transaction engine level.
4. **Strict Principal Binding:** The consuming principal must match the requesting principal (`ticket.principal_id == principal_id`). Generic string bypasses (`"human"`, `"all"`) are completely eliminated.
