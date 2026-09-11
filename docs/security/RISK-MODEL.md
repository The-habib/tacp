# TACP Risk & Autonomy Classification Engine

**Document:** `docs/security/RISK-MODEL.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**Security Lead:** Antigravity Principal Security Engineer  
**Date:** September 11, 2026  

---

## 1. Principles of Risk & Autonomy

1. **Risk is an Input to Policy, Not Authorization**: Assigning an operation a risk level of `R1` does not automatically authorize it. The risk level is evaluated by the Policy Engine against the principal's current Autonomy Level and active approvals.
2. **Capabilities Cannot Self-Assign Autonomy**: A capability declares its baseline risk, but the runtime environment computes effective risk based on target resource, blast radius, reversibility, and caller parameters.
3. **Conservative Risk Escalation**: If any attribute of an operation is uncertain or touches multiple sensitivity zones, the risk score automatically escalates to the higher tier.

---

## 2. The 6 Risk Levels (R0 to R5)

| Risk Level | Name | Definition & Impact | Examples in TACP | Reversibility Guarantee |
|---|---|---|---|---|
| **R0** | **Observation** | Read-only inspection with zero side-effects on system or data | `system.info`, `fs.read`, `process.list`, `audit.recent` | Pure read; 100% reversible (no-op) |
| **R1** | **Low-Impact Mutation** | Minor, easily reversible file changes in temporary/scratch space | Creating a temporary build artifact, running code formatter | Fully reversible by deletion |
| **R2** | **Moderate Mutation** | Governed source code mutation or bounded test execution within workspace | `workspace.patch` on single file, running `pytest` in workspace | Reversible via snapshot / git checkout |
| **R3** | **Sensitive Operation** | Multi-file mutation, file deletion, package installation, or network query | Deleting files in workspace, `uv pip install`, git push | Partially reversible; may affect dependencies |
| **R4** | **High-Impact Operation** | System configuration modification, process termination, service restart | Terminating foreign processes, modifying Termux configs | Difficult to reverse; potential process loss |
| **R5** | **Critical Operation** | Privilege escalation, policy modification, secret access, destructive purge | Modifying TACP policy DB, accessing API keys, workspace purge | Irreversible; high blast radius |

---

## 3. The 6 Autonomy Levels (L0 to L5)

Each agent principal operates under a declared Autonomy Level that caps the maximum risk it can execute without requiring explicit human approval:

| Level | Designation | Permitted Automatic Execution | Human Intervention Requirement |
|---|---|---|---|
| **L0** | **OBSERVE** | `R0` only (Read-only) | All mutations and commands require approval |
| **L1** | **SUGGEST** | `R0` only | AI proposes diffs or commands; human must trigger execution |
| **L2** | **LOW_RISK_EXECUTE**| Up to `R1` | `R2` through `R5` require approval |
| **L3** | **WORKSPACE_AUTONOMY**| Up to `R2` within registered workspace | `R3` through `R5` require approval (Default for TACP agents) |
| **L4** | **EXTENDED_AUTONOMY** | Up to `R3` within workspace and test harness | `R4` and `R5` require approval |
| **L5** | **PRIVILEGED** | Up to `R5` (Reserved for authenticated Human/Local Operator)| Zero approvals required (Human owner only) |

---

## 4. Risk Evaluation Algorithm

The `RiskEngine` calculates the effective risk of an operation by combining:
1. **Capability Base Risk**: The static risk rating of the capability.
2. **Resource Sensitivity**: Target path or object classification (e.g. `.env` vs `main.py`).
3. **Operation Blast Radius**: Number of files affected, size of change, or network involvement.
4. **Reversibility**: Availability of a verified pre-mutation snapshot.

```python
class RiskEngine:
    def calculate_risk(
        self,
        capability: Capability,
        resource: Resource,
        parameters: Dict[str, Any],
        has_snapshot: bool,
    ) -> RiskLevel:
        base_risk = capability.base_risk

        # Escalate if target is sensitive or private
        if resource.classification in [DataClassification.SECRET, DataClassification.CRITICAL]:
            return RiskLevel.R5
        if resource.classification == DataClassification.SENSITIVE:
            base_risk = max(base_risk, RiskLevel.R3)

        # Escalate if modifying outside workspace
        if resource.trust_zone != TrustZone.WORKSPACE:
            base_risk = max(base_risk, RiskLevel.R4)

        # Escalate if mutation is irreversible and lacks snapshot
        if capability.is_mutating and not has_snapshot:
            base_risk = max(base_risk, RiskLevel.R3)

        # Multi-file blast radius check
        if parameters.get("file_count", 1) > 5:
            base_risk = max(base_risk, RiskLevel.R3)

        return base_risk
```

---

## 5. Autonomy vs. Risk Gating Matrix

When an agent requests an action, the Policy Engine compares computed Risk against the agent's Autonomy Level:

```
                  +-----------------------------------------------+
                  |                   RISK LEVEL                  |
                  |   R0    |   R1    |   R2    |   R3    |   R4/R5 |
+-----------------+---------+---------+---------+---------+---------+
| L0 (Observe)    |  ALLOW  | APPROVE | APPROVE | APPROVE | APPROVE |
| L1 (Suggest)    |  ALLOW  | APPROVE | APPROVE | APPROVE | APPROVE |
| L2 (Low-Risk)   |  ALLOW  |  ALLOW  | APPROVE | APPROVE | APPROVE |
| L3 (Workspace)  |  ALLOW  |  ALLOW  |  ALLOW  | APPROVE | APPROVE |
| L4 (Extended)   |  ALLOW  |  ALLOW  |  ALLOW  |  ALLOW  | APPROVE |
| L5 (Privileged) |  ALLOW  |  ALLOW  |  ALLOW  |  ALLOW  |  ALLOW  |
+-----------------+---------+---------+---------+---------+---------+
```

*Rule*: Any cell marked `APPROVE` automatically shifts the policy decision to `REQUIRE_APPROVAL`.
