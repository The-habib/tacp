# TACP Phase 6: Security Test Matrix & Verification Architecture
**Document ID:** `TACP-TEST-MAT-001`  
**Classification:** Test Engineering & Adversarial Verification Specification  
**Release Target:** v0.5.0-alpha / Phase 6  
**Date:** September 2026  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Test Architecture Overview

Phase 6 introduces new governance primitives (Risk Ladder, Trust Profiles, Capability Leases, Grouped Approvals, and Caches). To maintain the zero-regression standard established in Phase 5, every new primitive is paired with comprehensive adversarial and sabotage tests.

---

## 2. Test Categories & Scenarios

### 2.1 Category 1: Trust Profile Enforcement Tests
- `test_profile_lockdown_blocks_all_mutations`: In `LOCKDOWN`, `workspace.patch` is unconditionally denied.
- `test_profile_lockdown_blocks_all_executions`: In `LOCKDOWN`, `execution.request` is unconditionally denied.
- `test_profile_strict_requires_approval_for_all_mutations`: In `STRICT`, single/batch patches require approval even if leases exist.
- `test_profile_developer_permits_bounded_patch_without_ticket`: In `DEVELOPER`, bounded workspace patches execute automatically.
- `test_profile_developer_retains_r4_r5_approval`: In `DEVELOPER`, sensitive system and emergency operations still require authorization.

### 2.2 Category 2: Capability Lease Lifecycle Tests
- `test_lease_valid_execution`: Valid lease permits $R_2$ patch without manual ticket.
- `test_lease_expired_rejected`: Expired lease falls back to `REQUIRE_APPROVAL`.
- `test_lease_wrong_principal_rejected`: Lease issued to Agent A rejected when presented by Agent B.
- `test_lease_wrong_workspace_rejected`: Lease issued for Workspace A rejected when used on Workspace B.
- `test_lease_wrong_capability_rejected`: Patch lease cannot authorize `execution.request`.
- `test_lease_risk_ceiling_enforced`: $R_2$ lease cannot authorize $R_3$ process execution.
- `test_lease_budget_decrement_and_exhaustion`: Lease budget decrements atomically on each call and blocks when 0.
- `test_lease_revocation_blocks_further_calls`: Revoked lease immediately rejected.
- `test_lease_concurrent_atomic_decrement`: Multithreaded concurrent calls cannot exceed budget.

### 2.3 Category 3: Approval Grouping & Plan Tests
- `test_plan_dry_run_returns_structured_summary`: Dry-run returns file list and byte counts without disk writes.
- `test_group_approval_exact_plan_hash_match`: Grouped approval ticket successfully commits whole batch.
- `test_group_approval_extra_file_fails_hash`: Adding an unauthorized file changes `plan_hash` and rejects ticket.
- `test_group_approval_path_alteration_fails_hash`: Modifying target subpath rejects ticket.
- `test_group_approval_double_consumption_prevented`: Replaying a consumed group token raises security error.

### 2.4 Category 4: Cache Invalidation & Consistency Tests
- `test_workspace_cache_hit_avoids_db_query`: Consecutive workspace operations reuse in-memory cache.
- `test_workspace_cache_invalidated_on_register`: Registering or updating a workspace invalidates cache.
- `test_stale_cache_cannot_grant_authorization`: Removing a workspace immediately invalidates cache; stale references fail closed.

### 2.5 Category 5: Tool Surface Dynamic Exposure Tests
- `test_lockdown_profile_hides_mutating_and_executing_tools`: `tools/list` returns only `OBSERVE` capabilities in `LOCKDOWN`.
- `test_disabled_flags_hide_tools`: `execution_enabled=False` removes `execution.request` from MCP tool listing.
- `test_tool_descriptions_contain_risk_and_approval_notices`: Every exposed tool definition contains structured risk and approval metadata.

### 2.6 Category 6: Realistic UX Workflow Scenarios (Part 41)
- **Scenario A:** "Inspect my project" -> Read-only operations (`workspace.inspect`, `fs.list`, `fs.read`) execute in < 10ms with zero approval prompts.
- **Scenario B:** "Find all references to X" -> `fs.search` returns bounded results instantly with zero friction.
- **Scenario C:** "Fix these three files" -> `dry_run=True` generates concise plan; single grouped approval commits all 3 files cleanly.
- **Scenario D:** "Run safe project verification" -> Process execution under active trust profile.
- **Scenario E:** "Run risky command" -> Rejected or gated by explicit human approval.
- **Scenario F:** "Do this forever" -> Blocked by bounded lease duration (maximum 60 minutes) and budget.

### 2.7 Category 7: Phase 6 Sabotage Tests (Part 39)
Intentional regression injection verifying that test suites catch every security bypass:
1. Sabotage: Disable risk classification.
2. Sabotage: Remove lease workspace scope check.
3. Sabotage: Remove approval plan hash verification.
4. Sabotage: Disable workspace cache invalidation.
5. Sabotage: Expose mutating tools under `LOCKDOWN`.
6. Sabotage: Allow remote agent to claim `LOCAL_HUMAN`.
7. Sabotage: Remove approval requirement for $R_3$ under `BALANCED`.
8. Sabotage: Permit lease duration > 3600 seconds.
9. Sabotage: Allow lease budget to decrement below zero.
10. Sabotage: Bypass audit log recording on leased actions.
