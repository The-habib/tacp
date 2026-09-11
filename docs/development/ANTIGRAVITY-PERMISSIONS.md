# Antigravity Permission Model Policy for Phase 2

**Document:** `docs/development/ANTIGRAVITY-PERMISSIONS.md`  
**Status:** ACTIVE POLICY (Phase 2)  
**Security Standard:** Least Privilege Principle  
**Date:** September 11, 2026  

---

## 1. Antigravity Permission Precedence

Antigravity evaluates permission decisions using the standard security hierarchy:
```
DENY > ASK > ALLOW
```

In accordance with Phase 2 Master Specification Part XLVIII:
- Wildcard defaults such as `mcp(*)`, `command(*)`, or `unsandboxed(*)` are **strictly forbidden**.
- Permissions are strictly project-scoped to `/data/data/com.termux/files/home/projects/tacp`.

---

## 2. Scoped Permission Tiers

### ALLOW (Safe Development Operations)
- Reading files within `/data/data/com.termux/files/home/projects/tacp`
- Running non-destructive development commands:
  - `./doctor`, `./verify`, `pytest`, `ruff`, `mypy`, `shellcheck`, `git status`, `git diff`, `git log`
- Editing source code, tests, and documentation inside the project workspace
- Staging and committing files to git feature branches

### ASK (Human Confirmation Required)
- Modifying repository configuration or GitHub CI workflows
- Merging branches to `main` or publishing release tags
- Installing new system packages via `pkg` or Python dependencies via `uv pip`
- Executing external network operations outside verified GitHub endpoints

### DENY (Permanently Forbidden)
- Invoking `su` or attempting root privilege escalation
- Accessing or modifying personal credentials (`~/.ssh`, `~/.config/gh`, `~/.termux`, Android private storage)
- Exposing unauthenticated network ports to the public internet
- Modifying agent governance rules or test runners to bypass verification failures
- Bypassing the 16-stage execution pipeline
