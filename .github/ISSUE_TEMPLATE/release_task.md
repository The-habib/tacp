---
name: Release Task
about: Track milestones and release verification checklists
title: "release: v"
labels: ["release"]
---

### 1. Target Release Version

### 2. Evidence Verification Checklist
- [ ] All PRs merged have attained E4 (CI Verified)
- [ ] `./verify` passes locally on clean checkout (E3)
- [ ] Threat model and security suite passes (E5)
- [ ] Real-device validation completed (E6)
- [ ] Changelog and compatibility matrix updated
- [ ] Human Owner sign-off acquired
