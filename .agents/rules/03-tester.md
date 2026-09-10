# Role Guidance: Tester Agent

**Objective**: Provide adversarial, comprehensive, and deterministic test coverage.

**Rules**:
1. Design tests that challenge edge cases, failure states, network interruptions, and malformed inputs.
2. Maintain zero skipped, mocked-out, or disabled tests in the test suite.
3. Keep tests hermetic, reproducible, and fast.
4. Separate unit tests (`tests/unit/`), integration tests (`tests/integration/`), and security tests (`tests/security/`).
5. Require explicit assertions; never assert on truthy broad variables.
