# TACP Phase 2 Requirement Traceability Matrix

**Document:** `docs/testing/PHASE-2-REQUIREMENT-TRACEABILITY.md`  
**Phase:** Phase 2 — Governed Execution Platform (Gate A Architecture)  
**QA Lead:** Antigravity QA & Verification Lead  
**Date:** September 11, 2026  

---

## 1. Traceability Standard & Purpose

This matrix maps every Part of the **Phase 2 Master Engineering Specification (Parts I through LXXXVI)** directly to its architectural design document, domain entity, implementation module, verification tests, and designated vertical slice.

---

## 2. Master Requirement Traceability Table

| Part # | Specification Title | Design Document | Implementation Module | Verification Test Suite | Target Slice |
|---|---|---|---|---|---|
| **I** | Repository Reconnaissance | `docs/phases/PHASE-2-CURRENT-STATE-AUDIT.md` | N/A (Audit) | `./verify` | Gate A |
| **II** | Baseline Freeze | `docs/baselines/TACP-0.1-READ-ONLY-CONTRACT.md` | `src/tacp/` | Read-only regression (269 tests) | Gate A |
| **III** | Architectural Model (5 Planes) | `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md` | `src/tacp/` plane layout | Plane boundary tests | Slice 1 |
| **IV** | Governed Execution Pipeline | `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md` | `src/tacp/control/pipeline.py` | `test_governed_pipeline.py` | Slice 1 |
| **V** | Domain Model | `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md` | `src/tacp/domain/` | `test_domain_models.py` | Slice 1 |
| **VI** | Principal & Identity | `docs/security/IDENTITY-MODEL.md` | `src/tacp/control/identity.py` | `test_identity_model.py` | Slice 1 |
| **VII** | Resource Model | `docs/execution/EXECUTION-CONTRACT.md` | `src/tacp/domain/resource.py` | `test_resource_model.py` | Slice 1 |
| **VIII**| Capability Model | `docs/mcp/MCP-PHASE-2-CONTRACT.md` | `src/tacp/core/capability_service.py` | `test_capability_registry.py`| Slice 1 |
| **IX** | Policy Engine | `docs/security/POLICY-MODEL.md` | `src/tacp/control/policy.py` | `test_policy_engine.py` | Slice 1 |
| **X** | Policy Hierarchy (5-tier) | `docs/security/POLICY-MODEL.md` | `src/tacp/control/policy.py` | `test_policy_hierarchy.py` | Slice 1 |
| **XI** | Autonomy Levels (L0-L5) | `docs/security/RISK-MODEL.md` | `src/tacp/control/risk.py` | `test_autonomy_levels.py` | Slice 1 |
| **XII** | Risk Engine (R0-R5) | `docs/security/RISK-MODEL.md` | `src/tacp/control/risk.py` | `test_risk_engine.py` | Slice 1 |
| **XIII**| Approval Engine | `docs/security/APPROVAL-MODEL.md` | `src/tacp/control/approval.py` | `test_approval_engine.py` | Slice 1 |
| **XIV** | Execution Contract | `docs/execution/EXECUTION-CONTRACT.md` | `src/tacp/domain/contract.py` | `test_execution_contract.py`| Slice 1 |
| **XV** | Workspace Model | `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md` | `src/tacp/core/workspace_service.py` | `test_workspace_service.py`| Slice 1 |
| **XVI** | Trust Zones (5 Zones) | `docs/security/PHASE-2-SECURITY-ARCHITECTURE.md` | `src/tacp/domain/classification.py` | `test_trust_zones.py` | Slice 1 |
| **XVII**| Data Classification (6 Tiers) | `docs/security/PHASE-2-SECURITY-ARCHITECTURE.md` | `src/tacp/domain/classification.py` | `test_data_classification.py`| Slice 1 |
| **XVIII**| Data != Instruction Separation | `docs/security/PHASE-2-SECURITY-ARCHITECTURE.md` | `src/tacp/control/pipeline.py` | `test_instruction_injection.py`| Slice 1 |
| **XIX** | First Mutation: `workspace.patch`| `docs/execution/PATCH-MODEL.md` | `src/tacp/core/patch_service.py` | `test_workspace_patch.py` | Slice 1 |
| **XX** | Patch Model | `docs/execution/PATCH-MODEL.md` | `src/tacp/domain/patch.py` | `test_patch_model.py` | Slice 1 |
| **XXI** | Filesystem Safety | `docs/execution/MUTATION-MODEL.md` | `src/tacp/providers/filesystem.py` | `test_security_matrix_88.py` (1-15)| Slice 1 |
| **XXII**| TOCTOU Resistance | `docs/execution/MUTATION-MODEL.md` | `src/tacp/providers/filesystem.py` | `test_toctou_races.py` | Slice 1 |
| **XXIII**| Atomic Mutation | `docs/execution/MUTATION-MODEL.md` | `src/tacp/providers/filesystem.py` | `test_atomic_writer.py` | Slice 1 |
| **XXIV**| Checkpoints & Snapshots | `docs/execution/RECOVERY-MODEL.md` | `src/tacp/core/snapshot_service.py` | `test_snapshot_service.py` | Slice 3 |
| **XXV** | Concurrency & Locks | `docs/execution/CONCURRENCY-MODEL.md` | `src/tacp/core/lock_service.py` | `test_concurrency_locks.py` | Slice 1 |
| **XXVI**| Capability Leases | `docs/execution/CONCURRENCY-MODEL.md` | `src/tacp/control/lease.py` | `test_capability_leases.py`| Slice 1 |
| **XXVII**| Command Execution (`execution.request`)| `docs/execution/JOB-MODEL.md` | `src/tacp/core/command_service.py` | `test_command_execution.py`| Slice 4 |
| **XXVIII**| Command Safety & Injections | `docs/execution/JOB-MODEL.md` | `src/tacp/providers/process.py` | `test_security_matrix_88.py` (27-38)| Slice 4 |
| **XXIX**| Command Policy Classification | `docs/execution/JOB-MODEL.md` | `src/tacp/control/policy.py` | `test_command_policy.py` | Slice 4 |
| **XXX** | Process Model | `docs/execution/JOB-MODEL.md` | `src/tacp/providers/process.py` | `test_process_provider.py` | Slice 4 |
| **XXXI**| Job System | `docs/execution/JOB-MODEL.md` | `src/tacp/core/job_service.py` | `test_job_service.py` | Slice 5 |
| **XXXII**| Long-Running Ops (No fake Tasks) | `docs/mcp/MCP-PHASE-2-CONTRACT.md` | `src/tacp/access/mcp/tools.py` | `test_mcp_job_tools.py` | Slice 5 |
| **XXXIII**| Resource Governor | `docs/execution/JOB-MODEL.md` | `src/tacp/core/governor_service.py`| `test_resource_governor.py`| Slice 5 |
| **XXXIV**| Circuit Breakers | `docs/execution/RECOVERY-MODEL.md` | `src/tacp/control/pipeline.py` | `test_circuit_breaker.py` | Slice 3 |
| **XXXV**| Network Policy | `docs/security/NETWORK-MODEL.md` | `src/tacp/control/network.py` | `test_network_policy.py` | Slice 4 |
| **XXXVI**| Secret Brokerage | `docs/security/SECRET-MODEL.md` | `src/tacp/core/secret_broker.py` | `test_secret_broker.py` | Slice 4 |
| **XXXVII**| Output Sanitization | `docs/security/SECRET-MODEL.md` | `src/tacp/infrastructure/logging.py` | `test_output_sanitizer.py`| Slice 1 |
| **XXXVIII**| Structured Audit Logging | `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md` | `src/tacp/core/audit_service.py` | `test_audit_service.py` | Slice 1 |
| **XXXIX**| Audit Integrity & Hash Chaining | `docs/baselines/TACP-0.1-READ-ONLY-CONTRACT.md` | `src/tacp/core/audit_service.py` | `test_audit_integrity.py` | Slice 1 |
| **XL** | Observability & Telemetry | `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md` | `src/tacp/core/system_service.py` | `test_system_service.py` | Slice 1 |
| **XLI** | Error Taxonomy (16+ Codes) | `docs/mcp/MCP-PHASE-2-CONTRACT.md` | `src/tacp/domain/errors.py` | `test_error_taxonomy.py` | Slice 1 |
| **XLII**| State Machine Validation | `docs/execution/JOB-MODEL.md` | `src/tacp/domain/` | `test_state_machines.py` | Slice 1 |
| **XLIII**| Idempotency Classification | `docs/execution/PATCH-MODEL.md` | `src/tacp/domain/capability.py` | `test_idempotency.py` | Slice 1 |
| **XLIV**| Domain Event Model | `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md` | `src/tacp/domain/events.py` | `test_domain_events.py` | Slice 1 |
| **XLV** | MCP 2026-07-28 Modernization | `docs/mcp/MCP-PHASE-2-CONTRACT.md` | `src/tacp/access/mcp/` | `test_mcp_contract.py` | Slice 1 |
| **XLVI**| MCP Tool Gate Checklist | `docs/mcp/MCP-PHASE-2-CONTRACT.md` | `src/tacp/access/mcp/tools.py` | `test_mcp_tool_gate.py` | Slice 1 |
| **XLVII**| OpenAI Secure Tunnel Readiness | `docs/mcp/OPENAI-TUNNEL-READINESS.md` | Stdio transport adapter | `test_openai_tunnel.py` | Slice 1 |
| **XLVIII**| Antigravity Permissions | `docs/development/ANTIGRAVITY-PERMISSIONS.md` | CLI config | Permissions audit | Gate A |
| **XLIX**| Feature Flags (Disabled by Default)| `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md` | `src/tacp/infrastructure/config.py`| `test_feature_flags.py` | Slice 1 |
| **L** | Configuration Safety | `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md` | `src/tacp/infrastructure/config.py`| `test_config.py` | Slice 1 |
| **LI** | Backward Compatibility | `docs/baselines/TACP-0.1-READ-ONLY-CONTRACT.md` | `src/tacp/` | Read-only regression (269 tests) | Slice 1-5 |
| **LII** | Database Migrations | `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md` | `src/tacp/infrastructure/migrations.py` | `test_migrations.py` | Slice 1 |
| **LIII**| Test Architecture (13 Classes) | `docs/testing/PHASE-2-TEST-PLAN.md` | `tests/` directory layout | Full pytest suite | Slice 1-5 |
| **LIV** | 200+ New Behavioral Tests | `docs/testing/PHASE-2-TEST-PLAN.md` | `tests/` test suites | Automated test count | Slice 1-5 |
| **LV** | 88 Security Test Matrix Cases | `docs/testing/PHASE-2-SECURITY-MATRIX.md` | `tests/security/test_security_matrix_88.py` | All 88 security tests | Slice 1-5 |
| **LVI** | Sabotage & Failure Injection | `docs/testing/PHASE-2-TEST-PLAN.md` | Verifier failure test harness | Sabotage suite | Slice 1 |
| **LVII**| Mutation Testing | `docs/testing/PHASE-2-TEST-PLAN.md` | Logic inversion harness | Mutation tests | Slice 1 |
| **LVIII**| Property & Fuzz Testing | `docs/testing/PHASE-2-TEST-PLAN.md` | Path fuzzing harness | Fuzz tests | Slice 1 |
| **LIX** | Concurrency Testing | `docs/execution/CONCURRENCY-MODEL.md` | Lock test suite | `test_concurrency_locks.py` | Slice 1 |
| **LX** | Crash & Recovery Testing | `docs/execution/RECOVERY-MODEL.md` | Crash test harness | `test_crash_recovery.py` | Slice 3 |
| **LXI** | Real Device Validation | `docs/11-DEVICE-VALIDATION.md` | `tests/device/` | Real Termux run | Slice 1-5 |
| **LXII**| Clean-Room Verification | `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md` | Isolated git clone | Clean-room test | Slice 1-5 |
| **LXIII**| Installer Hardening | `install.sh` | Shell script flags | `test_installer.py` | Slice 1 |
| **LXIV**| Documentation Updates | All docs in `docs/` | Repository markdown | Docs consistency check | Slice 1-5 |
| **LXV** | Release Evidence Standard | `docs/13-EVIDENCE-STANDARD.md` | `docs/evidence/` | Evidence manifest | Slice 1-5 |
| **LXVI**| Evidence-Backed Performance | `docs/testing/PERFORMANCE-RESULTS.json`| `scripts/measure_performance.py`| Performance benchmark | Slice 1-5 |
| **LXVII**| Auditable Change History | Git & GitHub PRs | Conventional Commits | Commit log audit | Slice 1-5 |
| **LXVIII**| Implementation Order | `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md` | Step 1 through 25 | Milestone roadmap | Slice 1-5 |
| **LXIX**| Vertical Slice Strategy | `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md` | Slices 1 through 5 | Slice delivery gates | Slice 1-5 |
| **LXX** | Vertical Slice 1 Contract | `docs/execution/PATCH-MODEL.md` | `workspace.patch` | Slice 1 test suite | Slice 1 |
| **LXXI**| No Direct MCP-to-OS Path | `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md` | `src/tacp/access/mcp/` | Negative API audit | Slice 1-5 |
| **LXXII**| 12 Security Invariants | `docs/security/PHASE-2-SECURITY-ARCHITECTURE.md` | Policy & Control Plane | Invariants 1-12 suite | Slice 1-5 |
| **LXXIII**| Emergency Local Stop | `docs/security/PHASE-2-SECURITY-ARCHITECTURE.md` | Sentinel file / SIGKILL | `test_emergency_stop.py` | Slice 1 |
| **LXXIV**| State Reconciliation | `docs/execution/RECOVERY-MODEL.md` | `tacp startup` reconciliation | `test_reconciliation.py` | Slice 3 |
| **LXXV**| Security Red Team Pass | `docs/testing/PHASE-2-SECURITY-MATRIX.md` | Adversarial test suite | Red team audit | Slice 5 |
| **LXXVI**| Independent Review Pass | `docs/phases/PHASE-2-DESIGN-REVIEW.md` | Reviewer Persona | Review reports | Gate A & B |
| **LXXVII**| GitHub Governance Audit | `docs/phases/PHASE-2-CURRENT-STATE-AUDIT.md`| GitHub API / settings | Governance gap record | Gate A |
| **LXXVIII**| Comprehensive CI Pipeline | `.github/workflows/` | GitHub Actions | CI matrix run | Slice 1-5 |
| **LXXIX**| Quality Gates (A through H) | `docs/releases/TACP-0.2-READINESS-PLAN.md` | Gate enforcement | Readiness sign-off | Slice 1-5 |
| **LXXX**| Release Status Classifications | `docs/releases/TACP-0.2-READINESS-PLAN.md` | Status labeling | Evidence standard | Slice 1-5 |
| **LXXXI**| Required Gate A Deliverables | `docs/phases/` & `docs/security/` | 19 design documents | Deliverables review | Gate A |
| **LXXXII**| Adversarial Design Review | `docs/phases/PHASE-2-DESIGN-REVIEW.md` | Architecture review | Blocker classification | Gate A |
| **LXXXIII**| Implementation Discipline | `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md` | Single-slice branches | Git history | Slice 1-5 |
| **LXXXIV**| Reporting to the CEO | Executive summaries | Structured reports | Slice reports | Slice 1-5 |
| **LXXXV**| Stop Conditions | `docs/phases/PHASE-2-GOVERNED-EXECUTION-DESIGN.md` | Safe halts | Human escalation | Gate A & B |
| **LXXXVI**| Phase 2 Success Criteria | `docs/releases/TACP-0.2-READINESS-PLAN.md` | 15 success criteria | Final sign-off | Slice 5 |
