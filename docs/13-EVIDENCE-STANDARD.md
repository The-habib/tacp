# TACP Evidence Standard

**Status**: BINDING STANDARD  

---

## 1. The Evidence Levels (E0 - E7)

Every feature, capability, bugfix, or release must be tagged with its attained Evidence Level:

- **E0 (Idea)**: Concept documented in issue or backlog. No design yet.
- **E1 (Designed)**: Architecture documented in PRD, ADR, or design doc.
- **E2 (Implemented)**: Source code written in repository branch.
- **E3 (Locally Tested)**: Passed `./verify` locally in Termux.
- **E4 (CI Verified)**: Passed GitHub Actions CI matrix on PR.
- **E5 (Security Verified)**: Passed threat model tests and `pip-audit`.
- **E6 (Device Verified)**: Executed and verified directly on real Android device.
- **E7 (Release Verified)**: Tagged release approved by Human Owner with full evidence manifest.

---

## 2. Invariant Rule

No pull request may be merged without attaining **E4**. No release tag may be issued without attaining **E7**.
