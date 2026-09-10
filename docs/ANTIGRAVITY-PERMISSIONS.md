# Antigravity Permission Model Policy

**Status**: ACTIVE POLICY  

---

## 1. Permission Categorization

Antigravity operations within the TACP project are governed by three categories:

### ALLOW (Safe Development Operations)
- Read files within `~/projects/tacp`
- Run non-destructive inspection commands (`git status`, `./verify`, `./doctor`, `pytest`)
- Edit source code, tests, and documentation inside `~/projects/tacp`

### ASK (Destructive, Network, or Privileged Operations)
- Modifying repository configuration or branch protection
- Publishing git tags or pushing to `main`
- Installing new system packages via `pkg`
- Network operations outside verified GitHub endpoints

### DENY (Forbidden Operations)
- Invoking `su` or attempting root privilege escalation
- Accessing or modifying personal configuration (`~/.ssh`, `~/.config/gh`, `~/.termux`)
- Exposing unauthenticated network ports to the public internet
- Modifying agent governance rules to bypass test failures
