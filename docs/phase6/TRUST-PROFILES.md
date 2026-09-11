# TACP Phase 6: Trust Profiles Specification
**Document ID:** `TACP-PROF-001`  
**Classification:** Security Architecture & Profile Specification  
**Release Target:** v0.5.0-alpha / Phase 6  
**Date:** September 2026  
**Governing Principle:** AI MAY BE AUTONOMOUS. AI MUST NEVER BE SOVEREIGN.

---

## 1. Concept & Purpose

A single static governance posture cannot serve all development phases:
- During active prototyping, requiring human approval on every single file edit causes severe approval fatigue.
- During production maintenance or untrusted code review, every mutation must be scrutinized.
- In security incident investigations, the entire environment should be strictly read-only.

TACP Phase 6 introduces **Trust Profiles** to give operators explicit, declarative control over the friction/security tradeoff.

---

## 2. Trust Profile Taxonomy

TACP defines four canonical trust profiles:

```
[ LOCKDOWN ] ──> Zero mutations. Zero executions. Strictly read-only observation.
[ STRICT ]   ──> Every mutation and execution requires explicit human approval.
[ BALANCED ] ──> (Default) Automatic reads. Bounded workspace edits via leases.
[ DEVELOPER] ──> Pre-approved low-risk workspace edits. Bounded process execution via leases.
```

### 2.1 Profile Comparison Matrix

| Capability / Risk Class | LOCKDOWN | STRICT | BALANCED (Default) | DEVELOPER |
|---|---|---|---|---|
| **$R_0$: Observation / Read** | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` |
| **$R_1$: Dry-Run Plans** | `ALLOW` | `ALLOW` | `ALLOW` | `ALLOW` |
| **$R_2$: Single File Patch** | `DENY` | `REQUIRE_APPROVAL` | `ALLOW_WITH_LEASE` / `REQUIRE_APPROVAL` | `ALLOW` (in workspace) |
| **$R_2$: Batch File Patch** | `DENY` | `REQUIRE_APPROVAL` | `ALLOW_WITH_LEASE` / `REQUIRE_APPROVAL` | `ALLOW_WITH_LEASE` |
| **$R_3$: Controlled Execution** | `DENY` | `REQUIRE_APPROVAL` | `REQUIRE_APPROVAL` | `ALLOW_WITH_LEASE` / `REQUIRE_APPROVAL` |
| **$R_4$: Sensitive / Network** | `DENY` | `DENY` | `REQUIRE_APPROVAL` | `REQUIRE_APPROVAL` |
| **$R_5$: Emergency Stop** | `ALLOW` (Human) | `ALLOW` (Human) | `ALLOW` (Human) | `ALLOW` (Human) |
| **MCP Tool Visibility** | Only $R_0$ tools exposed | All tools exposed | All tools exposed | All tools exposed |

---

## 3. What Trust Profiles CANNOT Do (Negative Invariants)

Trust profiles are **attenuation mechanisms**, not privilege escalation tools. A trust profile can only reduce approval friction within pre-existing, rigorously validated security boundaries.

Under NO trust profile (even `DEVELOPER`) can TACP:
1. Grant root or administrative OS privileges.
2. Permit arbitrary shell execution (`bash -c`, `sh`, `os.system()`).
3. Spawn non-allowlisted binaries (e.g. `rm`, `curl`, `python`, `git`).
4. Bypass workspace directory jailing or traversal checks.
5. Bypass secret redaction or environment sanitization.
6. Disable or alter audit logging.
7. Override or ignore emergency stop commands.
8. Authorize operations outside designated workspace roots.

---

## 4. Configuration & Activation

Trust profiles are configured in `tacp.toml` or via environment variable `TACP_TRUST_PROFILE`:

```toml
[governance]
trust_profile = "BALANCED"  # Options: STRICT, BALANCED, DEVELOPER, LOCKDOWN
lease_default_duration_seconds = 1200 # 20 minutes
lease_max_duration_seconds = 3600     # 60 minutes
```

CLI subcommands allow viewing and setting profiles:
```bash
tacp profile show
tacp profile set STRICT
tacp profile set LOCKDOWN
```

Changing the trust profile automatically invalidates all active capability leases, forcing re-evaluation under the new security posture.
