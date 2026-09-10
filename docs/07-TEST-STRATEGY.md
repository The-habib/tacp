# TACP Test Strategy & QA Framework

**Status**: ACTIVE BASELINE  
**QA Lead**: Antigravity QA Lead  

---

## 1. The Quality Pyramid

```
                     [ Release Verification (E7) ]
                    /                                          [ Real Android Device Verification (E6) ]
            /                                              [ Security & Penetration Suites (E5)               ]
    /                                                       [ GitHub Actions CI Matrix (E4)                           ]
 /                                                             [ Canonical Local Verifier (./verify) - Unit, Type, Lint (E3)    ]
```

---

## 2. Test Classification

1. **Unit Tests (`tests/unit/`)**: Fast, hermetic tests validating discrete pure functions, schemas, and policy decision logic. Zero external network or hardware dependencies.
2. **Integration Tests (`tests/integration/`)**: Validates component interactions, SQLite transactions, and MCP message framing.
3. **Security Tests (`tests/security/`)**: Adversarial tests validating path traversal defenses, secret leakage prevention, command injection guards, and input fuzzing.
4. **Device Tests (`tests/device/`)**: Validates real Termux/Android behavior (Termux wake locks, battery levels, process tree signals).

---

## 3. Strict Rules for Test Execution

- **Zero Tolerance for Skipping**: No `pytest.mark.skip` or commented-out assertions without prior ADR authorization.
- **Fail Loud**: Assertions must provide detailed diffs.
- **Deterministic**: Tests must not depend on order of execution or external network state.
