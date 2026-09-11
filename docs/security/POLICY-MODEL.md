# TACP Policy Engine & Hierarchy Model

**Document:** `docs/security/POLICY-MODEL.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**Security Lead:** Antigravity Principal Security Engineer  
**Date:** September 11, 2026  

---

## 1. Policy Principles

1. **Default-Deny Everywhere**: Any action, resource, or capability not explicitly permitted by a valid, active policy rule is denied.
2. **Strict Hierarchy (Downward Restriction Only)**: Lower policy layers can only *narrow* or *restrict* authority granted by higher layers; they can *never* expand, grant, or elevate permissions beyond their parent layer.
3. **Ambiguity Fails Closed**: If policy rules conflict, cannot be evaluated, or return ambiguous results, the decision MUST resolve to `DENY` or `REQUIRE_APPROVAL`. It never defaults to `ALLOW`.
4. **AI Policy Mutation Immunity**: Policy rules are immutable to AI agents. No tool exists for an AI agent to alter, append, or delete policies.

---

## 2. The 5-Tier Policy Hierarchy

Policies are evaluated in a strict top-down cascade. The most restrictive decision among all matching layers wins:

```
+------------------------------------------------------------------------+
| 1. PLATFORM POLICY (System-wide constitutional invariants)             |
|    - Defined in TACP source code; cannot be overridden by DB or user   |
|    - Examples: Root execution forbidden; /system writes denied;        |
|      secrets in ~/.ssh blocked; max path length 4096 chars.           |
+------------------------------------------------------------------------+
                                    │
                                    v
+------------------------------------------------------------------------+
| 2. USER POLICY (Device owner / CEO operational preferences)             |
|    - Configured by human via CLI or config file (`~/.tacp/config.toml`)|
|    - Examples: Max agent autonomy = L3; require approval for all shell |
|      commands; global budget = $5.00/day or 500 tasks.                |
+------------------------------------------------------------------------+
                                    │
                                    v
+------------------------------------------------------------------------+
| 3. WORKSPACE POLICY (Boundaries specific to a project directory)        |
|    - Associated with registered workspace in SQLite                    |
|    - Examples: Trust zone = WORKSPACE; git commit allowed;            |
|      network egress disabled; file patch max lines = 500.              |
+------------------------------------------------------------------------+
                                    │
                                    v
+------------------------------------------------------------------------+
| 4. SESSION POLICY (Constraints on an active MCP connection / lease)    |
|    - Defined during authentication or lease generation                |
|    - Examples: Session expiry = 30 minutes; allowed capabilities =     |
|      ['fs.read', 'workspace.patch']; read-only override active.        |
+------------------------------------------------------------------------+
                                    │
                                    v
+------------------------------------------------------------------------+
| 5. TASK POLICY (Narrow scope bound to a specific ExecutionContract)    |
|    - Declared per unit of work                                         |
|    - Examples: Target file = 'src/app.py' ONLY; timeout = 30s;         |
|      memory limit = 128 MB.                                            |
+------------------------------------------------------------------------+
```

---

## 3. Decision Types

The policy engine returns one of four formal `PolicyDecision` states:

| Decision State | Meaning | Execution Consequence |
|---|---|---|
| `ALLOW` | Operation is authorized under current policy | Pipeline proceeds to next stage |
| `DENY` | Operation is strictly forbidden by policy | Pipeline halts; `TacpSecurityError` raised |
| `REQUIRE_APPROVAL` | Permissible only with explicit human approval | Pipeline halts; approval request ticket created |
| `DEFER` | Resource is currently locked or budget pending | Pipeline defers execution or enqueues task |

---

## 4. Policy Evaluation Engine Algorithm

```python
class PolicyEngine:
    def evaluate(self, request: ExecutionRequest) -> PolicyDecision:
        # Step 1: Evaluate Platform Policy (Constitutional Rules)
        platform_decision = self.eval_platform_policy(request)
        if platform_decision.is_deny():
            return platform_decision

        # Step 2: Evaluate User Policy
        user_decision = self.eval_user_policy(request)
        if user_decision.is_deny():
            return user_decision

        # Step 3: Evaluate Workspace Policy
        workspace_decision = self.eval_workspace_policy(request)
        if workspace_decision.is_deny():
            return workspace_decision

        # Step 4: Evaluate Session Policy
        session_decision = self.eval_session_policy(request)
        if session_decision.is_deny():
            return session_decision

        # Step 5: Evaluate Task Policy
        task_decision = self.eval_task_policy(request)
        if task_decision.is_deny():
            return task_decision

        # Step 6: Consolidate Approvals
        # If any layer requires approval, the consolidated decision is REQUIRE_APPROVAL
        decisions = [
            platform_decision,
            user_decision,
            workspace_decision,
            session_decision,
            task_decision,
        ]
        if any(d.decision == DecisionType.REQUIRE_APPROVAL for d in decisions):
            approval_reasons = [
                d.reason for d in decisions if d.decision == DecisionType.REQUIRE_APPROVAL
            ]
            return PolicyDecision(
                decision=DecisionType.REQUIRE_APPROVAL,
                reason="; ".join(approval_reasons),
                risk_level=request.risk_level,
            )

        # Step 7: All layers ALLOW
        return PolicyDecision(
            decision=DecisionType.ALLOW,
            reason="Authorized by all policy hierarchy layers",
            risk_level=request.risk_level,
        )
```

---

## 5. Persistence Schema

```sql
CREATE TABLE IF NOT EXISTS policies (
    id TEXT PRIMARY KEY,
    layer TEXT NOT NULL CHECK(layer IN ('USER', 'WORKSPACE', 'SESSION', 'TASK')),
    scope_id TEXT,  -- workspace_id, session_id, or task_id
    name TEXT NOT NULL,
    rules_json TEXT NOT NULL,  -- Structured rule expressions
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_policies_layer_scope ON policies(layer, scope_id);
```

---

## 6. Safety Invariants

1. **Hierarchy Integrity Check**: During policy compilation, if a `WORKSPACE` policy attempts to permit an action denied by `PLATFORM` or `USER` policy, compilation fails with `PolicyEscalationError`.
2. **Atomic Policy Loads**: Policy changes reload atomically. A partial or malformed policy file fails closed and restores the previous valid policy.
3. **Audit Trail**: Every policy evaluation (including rule matched, duration, and decision) is logged in the cryptographic audit trail.
