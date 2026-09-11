# Evidence: Remote Trust Boundary & Principal Model

## Principal Identification
* **Class**: `Principal`
* **Type**: `PrincipalType.REMOTE_AI`
* **Credential Source**: `CredentialSource.TUNNEL`
* **Trust Tier**: `TrustTier.RESTRICTED`

## Invariant Verification
1. `principal.is_elevated() == False` (Enforced across all executions).
2. Remote AI cannot inherit `LOCAL_HUMAN` operator capabilities.
3. Capability leases requested by `REMOTE_AI` are rejected by `PolicyEngine`.
4. Disabling remote access via `TACP_REMOTE_ENABLED=false` results in immediate fail-closed denial of all remote requests.

## Test Suite Validation
`tests/unit/test_remote_governance.py` validates identity creation, authority bounding, lease denial, and fail-closed behavior across 9 unit tests.
