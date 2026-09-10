# TACP Development Workflow & Lifecycle

**Status**: ACTIVE & BINDING  

---

## 1. The Canonical Lifecycle

```
PRODUCT REQUIREMENT (PRD / CEO)
       ↓
GITHUB ISSUE (Tagged & Scoped)
       ↓
ARCHITECTURE CHECK (Does this require an ADR?)
       ↓
ANTIGRAVITY PLAN (/plan Artifact Approved by Human)
       ↓
IMPLEMENTATION (Small, cohesive changes + Tests)
       ↓
LOCAL VERIFICATION (./verify passes cleanly)
       ↓
SECURITY VERIFICATION (tests/security passes)
       ↓
COMMIT (Conventional Commit message)
       ↓
PULL REQUEST (Evidence checklist completed)
       ↓
GITHUB CI (Automated validation)
       ↓
REVIEW (Independent Reviewer Agent + Human sign-off)
       ↓
MERGE (Squash/Rebase into main)
       ↓
REAL TERMUX VALIDATION (On-device confirmation)
       ↓
RELEASE
```

---

## 2. Commit Conventions

Follow Conventional Commits:
- `feat(scope): ...` — New user-facing capability
- `fix(scope): ...` — Bug fix (must include regression test)
- `docs(scope): ...` — Documentation updates
- `test(scope): ...` — Adding or modifying tests
- `chore(scope): ...` — Tooling, linting, packaging
- `sec(scope): ...` — Security improvements or mitigations
