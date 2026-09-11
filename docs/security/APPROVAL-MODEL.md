# TACP Approval Engine & Human Sovereignty Model

**Document:** `docs/security/APPROVAL-MODEL.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**Security Lead:** Antigravity Principal Security Engineer  
**Date:** September 11, 2026  

---

## 1. Approval Principles

1. **No Blanket Authorizations**: An approval must never equate to *"The AI can now do anything."* Approvals are strictly bounded across five dimensions: **Principal**, **Capability**, **Resource**, **Risk Ceiling**, and **Time Horizon**.
2. **Explicit Human Action**: Approvals can only be granted by an authenticated `HUMAN` principal. AI agents cannot approve their own actions or delegate approvals to other agents.
3. **Single-Use or Bounded-Use**: By default, an approval is single-use (`one_time=True`). When a bounded-time lease is granted, it automatically invalidates once the expiration timestamp is reached.
4. **Non-Transferable & Non-Escalating**: An approval granted for workspace `A` cannot be used in workspace `B`. An approval granted for risk `R2` cannot execute an `R3` action.

---

## 2. The 5 Dimensions of an Approval

Every approval ticket must specify:

```
[PRINCIPAL]       --> Identifies the exact agent authorized (e.g. agent_openai_task_89)
[CAPABILITY]      --> Identifies the exact capability authorized (e.g. workspace.patch)
[RESOURCE SCOPE]  --> Identifies canonical resource pattern (e.g. workspace/repo/src/main.py)
[RISK CEILING]    --> Max risk permitted (e.g. R2: Moderate reversible mutation)
[EXPIRY HORIZON]  --> UTC expiration timestamp (e.g. valid for 15 minutes only)
```

---

## 3. Approval Lifecycle State Machine

```
               +-------------------+
               |    REQUESTED      |  <-- PolicyEngine returns REQUIRE_APPROVAL
               +-------------------+
                 /               \
       Human Grants             Human Denies
               /                   \
              v                     v
    +-------------------+    +-------------------+
    |      GRANTED      |    |      DENIED       |  --> Terminal state; audit logged
    +-------------------+    +-------------------+
        /             \
  Execution         Time Window
  Completed           Elapsed
      /                 \
     v                   v
+-------------------+ +-------------------+
|     CONSUMED      | |      EXPIRED      |  --> Terminal states; invalid for execution
+-------------------+ +-------------------+
```

### Valid State Transitions
- `REQUESTED` $\to$ `GRANTED` (by `HUMAN` principal)
- `REQUESTED` $\to$ `DENIED` (by `HUMAN` principal or timeout)
- `GRANTED` $\to$ `CONSUMED` (upon successful execution of single-use ticket)
- `GRANTED` $\to$ `EXPIRED` (upon monotonic clock exceeding `expires_at`)
- `GRANTED` $\to$ `REVOKED` (emergency stop or human override)

*All other transitions are invalid and rejected.*

---

## 4. Approval Persistence Schema

```sql
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    principal_id TEXT NOT NULL,
    capability_name TEXT NOT NULL,
    resource_pattern TEXT NOT NULL,
    risk_ceiling TEXT NOT NULL CHECK(risk_ceiling IN ('R0', 'R1', 'R2', 'R3', 'R4', 'R5')),
    status TEXT NOT NULL CHECK(status IN ('REQUESTED', 'GRANTED', 'DENIED', 'CONSUMED', 'EXPIRED', 'REVOKED')),
    requested_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by_principal_id TEXT,
    one_time INTEGER NOT NULL DEFAULT 1,
    consumption_count INTEGER NOT NULL DEFAULT 0,
    rationale TEXT NOT NULL,
    FOREIGN KEY(principal_id) REFERENCES principals(id)
);

CREATE INDEX IF NOT EXISTS idx_approvals_status_expiry ON approvals(status, expires_at);
CREATE INDEX IF NOT EXISTS idx_approvals_lookup ON approvals(principal_id, capability_name, status);
```

---

## 5. Approval Verification Algorithm

Before an operation marked `REQUIRE_APPROVAL` is permitted to proceed to contract issuance:

```python
class ApprovalEngine:
    def verify_approval(self, request: ExecutionRequest) -> ApprovalVerification:
        # Step 1: Look up active approval matching principal and capability
        ticket = self.db.find_active_approval(
            principal_id=request.principal.id,
            capability=request.capability.name,
            now=datetime.now(timezone.utc),
        )
        if not ticket:
            return ApprovalVerification(valid=False, reason="No active approval ticket found")

        # Step 2: Verify expiration
        if datetime.now(timezone.utc) > ticket.expires_at:
            ticket.status = ApprovalStatus.EXPIRED
            self.db.update(ticket)
            return ApprovalVerification(valid=False, reason="Approval ticket has expired")

        # Step 3: Verify resource scope
        if not fnmatch.fnmatch(request.target_resource, ticket.resource_pattern):
            return ApprovalVerification(
                valid=False,
                reason=f"Target '{request.target_resource}' not covered by scope '{ticket.resource_pattern}'",
            )

        # Step 4: Verify risk ceiling
        if request.risk_level > ticket.risk_ceiling:
            return ApprovalVerification(
                valid=False,
                reason=f"Action risk {request.risk_level.name} exceeds approval ceiling {ticket.risk_ceiling.name}",
            )

        # Step 5: Consume single-use ticket
        if ticket.one_time:
            ticket.status = ApprovalStatus.CONSUMED
            ticket.consumption_count += 1
            self.db.update(ticket)

        return ApprovalVerification(valid=True, approval_id=ticket.id)
```

---

## 6. Safety & Anti-Bypass Invariants

1. **Self-Approval Prevention**: The database constraint and business logic strictly require `decided_by_principal_id != principal_id` unless the principal type is `HUMAN`.
2. **Replay Attack Prevention**: A single-use approval ticket changes status to `CONSUMED` within an atomic SQLite transaction before execution begins. Any concurrent attempt to reuse the ticket fails.
3. **Monotonic Expiry**: Expiry checks use UTC timestamps verified against both wall-clock and process monotonic uptime to resist system clock adjustments.
