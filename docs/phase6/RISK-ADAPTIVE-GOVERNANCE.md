# TACP Phase 6: Risk-Adaptive Governance Framework
**Document ID:** `TACP-GOV-RISK-001`  
**Classification:** Governance & Policy Architecture  
**Release Target:** v0.5.0-alpha / Phase 6  
**Date:** September 2026  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Executive Philosophy

Binary security models ("allow all" vs. "prompt for everything") inevitably produce either critical vulnerabilities or user approval fatigue. When users are bombarded with approval dialogs for routine, reversible operations, they rapidly develop a habit of blindly approving all requests.

TACP Phase 6 introduces a **Risk-Adaptive Governance Framework** that dynamically calibrates security controls to the material risk of each operation.

---

## 2. The 6-Level Risk Ladder

Every capability invocation is classified into an explicit risk level ($R_0$ through $R_5$):

```
[ R5: CRITICAL / PRIVILEGED ] -------- (Emergency Stop, Policy Mutations, Admin Wipe)
        │
[ R4: SENSITIVE / NETWORK ] ---------- (External Network Access, Sensitive Credentials)
        │
[ R3: CONTROLLED PROCESS ] ----------- (OS Process Execution: printf, echo, true)
        │
[ R2: BOUNDED MUTATION ] ------------- (Single/Batch File Patches inside Workspace Jail)
        │
[ R1: LOW-IMPACT REVERSIBLE ] -------- (Dry-Run Evaluations, Transient Scratch Files)
        │
[ R0: OBSERVATION / READ-ONLY ] ------ (fs.read, fs.list, fs.stat, workspace.inspect)
```

### Risk Level Definitions:

| Risk Level | Name | Description | Reversibility | Capabilities Included |
|---|---|---|---|---|
| **$R_0$** | **Observation** | Non-mutating inspection of authorized workspace or system diagnostics. | N/A (Zero side effects) | `system.*`, `workspace.inspect`, `fs.read`, `fs.list`, `fs.stat`, `fs.search`, `process.*`, `audit.recent` |
| **$R_1$** | **Low-Impact Reversible** | Hypothetical plan generation, dry-runs, or sandbox queries that do not alter state. | Immediate (No state change) | `workspace.patch` (dry_run), `workspace.patch_batch` (dry_run), `execution.request` (dry_run) |
| **$R_2$** | **Bounded Mutation** | Modification of existing files strictly inside the validated workspace jail. | Fully Reversible (Snapshot & rollback support) | `workspace.patch`, `workspace.patch_batch` |
| **$R_3$** | **Controlled Process** | Spawning allowlisted operating-system processes in isolated process groups. | Partial / Bounded (Standard output capture only) | `execution.request` (`printf`, `echo`, `true`) |
| **$R_4$** | **Sensitive / Network** | Operations touching external network boundaries or sensitive tokens. | Irreversible | Scoped API bridges, external network (future Phase 7+) |
| **$R_5$** | **Critical / Privileged** | Modifying control plane policies, killing all processes, or admin configuration. | Irreversible / System-wide | `emergency_stop`, policy reconfiguration, audit purge attempts (denied) |

---

## 3. Four Policy Outcomes

Under risk-adaptive governance, policy decisions are no longer a simple boolean (`ALLOW`/`DENY`). The policy engine returns one of four formal outcomes:

1. **`ALLOW`:** The operation is permitted to execute immediately without human intervention.
2. **`ALLOW_WITH_LEASE`:** The operation is permitted to execute automatically if and only if the caller presents an active, valid, unexpired `CapabilityLease` bound to the workspace and risk ceiling.
3. **`REQUIRE_APPROVAL`:** The operation is halted. An `ApprovalTicket` is issued, requiring explicit out-of-band operator consent.
4. **`DENY`:** The operation is unconditionally blocked (e.g. traversal attempt, non-allowlisted binary, or violation of active trust profile).

---

## 4. Policy Decision Matrix by Risk & Profile

| Risk Level | Strict Profile | Balanced Profile (Default) | Developer Profile | Lockdown Profile |
|---|---|---|---|---|
| **$R_0$ (Read)** | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` |
| **$R_1$ (Dry Run)** | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` |
| **$R_2$ (Mutation)** | `REQUIRE_APPROVAL` | `ALLOW_WITH_LEASE` (or `REQUIRE_APPROVAL`) | `ALLOW` (bounded workspace) | `DENY` |
| **$R_3$ (Execution)** | `REQUIRE_APPROVAL` | `REQUIRE_APPROVAL` | `ALLOW_WITH_LEASE` (or `REQUIRE_APPROVAL`) | `DENY` |
| **$R_4$ (Network)** | `DENY` | `REQUIRE_APPROVAL` | `REQUIRE_APPROVAL` | `DENY` |
| **$R_5$ (Critical)** | `REQUIRE_APPROVAL` | `REQUIRE_APPROVAL` | `REQUIRE_APPROVAL` | `DENY` |

---

## 5. Defense-in-Depth Invariants

1. **Leases Cannot Override Security Boundaries:** A lease granting $R_2$ authority cannot be used to execute $R_3$ processes, escape a workspace, or access unlisted files.
2. **Deterministic Fallback:** If a lease is expired, revoked, or parameter-mismatched, the decision automatically falls back to `REQUIRE_APPROVAL`.
3. **Emergency Stop Precedence:** The emergency stop capability operates outside lease grants and immediately terminates all active operations regardless of profile.
