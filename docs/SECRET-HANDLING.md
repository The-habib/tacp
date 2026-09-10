# TACP Secret Handling & Security Governance

**Status**: BINDING POLICY  

---

## 1. Zero-Secret Invariant

1. Never commit real secrets, private keys, API keys, bearer tokens, or sensitive credentials into Git.
2. Never store secrets in test fixtures (`tests/fixtures/` must use only synthetic placeholders).
3. Never output secret values in logs, test output, or GitHub Actions CI runs.
4. When inspecting environment variables, inspect variable NAMES only.

---

## 2. Secret Incident Response Procedure

If a secret is ever detected in git history:
1. **Immediate Revocation**: The exposed secret must be revoked immediately at the provider.
2. **History Rewrite**: Git history must be purged using `git filter-repo` or equivalent.
3. **Audit**: An incident report must be filed in `docs/adr/`.
