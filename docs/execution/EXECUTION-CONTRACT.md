# TACP Execution Contract Specification

**Document:** `docs/execution/EXECUTION-CONTRACT.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**Execution Lead:** Antigravity Principal Execution Engineer  
**Date:** September 11, 2026  

---

## 1. Concept & Invariant

In TACP Phase 2, **no executor, provider, or subsystem accepts raw, unvalidated caller dictionaries**.

Every mutating or executing operation must be bound into an immutable, fully validated **`ExecutionContract`** issued by the Control Plane before any provider method is invoked.

### The Contract Invariant
```
[FORBIDDEN]  Executor.run(args: Dict[str, Any])
[REQUIRED]   ControlPlane.issue_contract(request) -> ExecutionContract
             Executor.run(contract: ExecutionContract)
```

An `ExecutionContract` encapsulates:
- Provenance (who requested it and why)
- Authorization (which policy, approval, and lease permitted it)
- Bounds (exact target files, resource limits, timeout, and output limits)
- Audit (cryptographic identifiers tying execution directly to evidence)

---

## 2. Structure of an ExecutionContract

```python
@dataclass(frozen=True)
class ExecutionContract:
    # 1. Identity & Provenance
    contract_id: str  # Unique UUIDv4 for this contract
    request_id: str  # Traceable request identifier
    trace_id: str  # Distributed client trace ID
    principal: Principal  # Authenticated actor initiating execution
    intent: str  # Stated user/agent objective
    task_id: Optional[str]  # Associated parent Task ID if part of a Plan

    # 2. Capability & Resource Scoping
    capability: Capability  # Formal capability being exercised
    target_resource: str  # Canonical target resource URI (e.g. workspace/ws-1/src/app.py)
    workspace: Workspace  # Canonical Workspace entity

    # 3. Governance & Risk
    policy_decision: PolicyDecision  # Validated policy decision (must be ALLOW)
    risk_level: RiskLevel  # Assessed risk rating (R0 to R5)
    approval_id: Optional[str]  # Consumed approval ticket ID (mandatory if risk > autonomy)
    lease_id: Optional[str]  # Active capability lease ID

    # 4. Constraints & Budgets
    timeout_seconds: int  # Hard wall-clock execution limit
    resource_budget: ResourceBudget  # CPU, memory, and disk write limits
    network_policy: NetworkPolicy  # Egress allowlist and transfer limits
    output_limits: OutputLimits  # Max stdout/stderr capture bytes

    # 5. Execution Parameters (Typed & Validated)
    parameters: Dict[str, Any]  # Strictly validated parameters adhering to capability schema

    # 6. Audit & State Tracking
    audit_id: str  # Pre-allocated audit event ID
    created_at: datetime  # Contract issuance timestamp (UTC)
```

---

## 3. Contract Lifecycle & Validation Flow

```
[1. Inbound Execution Request]
              │
              v
[2. Control Plane Verification]
      ├── Principal active?
      ├── Capability recognized?
      ├── Resource within workspace jail?
      ├── Schema valid?
      ├── Policy permits?
      ├── Risk <= Autonomy OR Approval valid?
      └── Concurrency lock acquired?
              │
              v
[3. Contract Issuance]       --> Creates frozen ExecutionContract
              │
              v
[4. Executor Dispatch]       --> Dispatches contract to concrete Provider
              │
              v
[5. Post-Execution Audit]    --> Binds contract_id to finalized AuditEvent
```

---

## 4. Safety & Immutability Guarantees

1. **Frozen Dataclass**: The `ExecutionContract` is an immutable Python `frozen=True` dataclass. Any attempt by an executor or middleware to mutate fields at runtime raises a `FrozenInstanceError`.
2. **Pre-Execution Checksum**: Before modifying a file or spawning a process, the contract verifies that the target resource matches the `base_checksum` recorded when the contract was issued. If the resource changed in the interim, execution aborts immediately with `ErrorCode.CONFLICT`.
3. **Audit Cross-Referencing**: The `contract_id` is recorded in all downstream child processes, patch headers, and audit log entries, providing 100% end-to-end traceability.
