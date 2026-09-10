# TACP Release Engineering & Governance

**Status**: ACTIVE BASELINE  
**Release Engineer**: Antigravity Release Engineer  

---

## 1. Semantic Versioning

TACP adheres strictly to **SemVer 2.0.0**:
```
MAJOR.MINOR.PATCH[-PRERELEASE]
```
- Current Phase: `0.1.0.dev0` (Bootstrap Engineering Foundation)

---

## 2. Release Gates & Evidence Level Requirement

No release tag may be published without satisfying **Evidence Level E7**:
1. `./verify` passes 100% cleanly on Termux.
2. GitHub Actions CI passes on all matrix versions.
3. Security test suite passes with zero vulnerabilities.
4. Real-device execution verified on Android 16.
5. Clean git working tree, signed git tag.
6. Explicit sign-off by Human Owner.
