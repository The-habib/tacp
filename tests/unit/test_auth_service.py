"""Unit tests for TACP TokenService and AuthToken."""

from datetime import datetime, timedelta, timezone

import pytest

from tacp.control.auth import (
    SCOPE_ADMIN,
    SCOPE_EXECUTE,
    SCOPE_FILES_READ,
    SCOPE_FILES_WRITE,
    SCOPE_PROCESS_READ,
    SCOPE_READ,
    SCOPE_SYSTEM_READ,
    AuthToken,
    TokenService,
    hash_token,
)
from tacp.control.identity import Authority, PrincipalType, TrustTier
from tacp.domain.errors import TacpValidationError
from tacp.infrastructure.database import Database


def test_create_and_validate_token(test_db: Database) -> None:
    service = TokenService(test_db)
    token, raw_secret = service.create_token(
        name="Claude Agent",
        scopes=[SCOPE_READ, SCOPE_FILES_WRITE],
        metadata={"client": "claude"},
    )

    assert token.id.startswith("tok_")
    assert raw_secret.startswith("tacp_sec_")
    assert token.name == "Claude Agent"
    assert token.scopes == [SCOPE_READ, SCOPE_FILES_WRITE]
    assert token.is_valid()
    assert not token.is_expired()
    assert token.token_hash == hash_token(raw_secret)

    # Validate with exact raw secret
    validated = service.validate_token(raw_secret)
    assert validated is not None
    assert validated.id == token.id
    assert validated.name == "Claude Agent"

    # Validate with Bearer prefix
    validated_bearer = service.validate_token(f"Bearer {raw_secret}")
    assert validated_bearer is not None
    assert validated_bearer.id == token.id


def test_token_hash_never_stores_secret(test_db: Database) -> None:
    service = TokenService(test_db)
    token, raw_secret = service.create_token("Secret Check")

    conn = test_db.connect()
    cursor = conn.cursor()
    cursor.execute("SELECT token_hash FROM auth_tokens WHERE id = ?", (token.id,))
    row = cursor.fetchone()
    stored_hash = row["token_hash"]

    assert stored_hash != raw_secret
    assert stored_hash == hash_token(raw_secret)


def test_token_revocation(test_db: Database) -> None:
    service = TokenService(test_db)
    token, raw_secret = service.create_token("Revocable Token")

    assert service.validate_token(raw_secret) is not None

    revoked = service.revoke_token(token.id)
    assert revoked is True

    # Now validation should return None
    assert service.validate_token(raw_secret) is None


def test_token_expiration(test_db: Database) -> None:
    service = TokenService(test_db)
    token, raw_secret = service.create_token("Expiring Token", expires_days=1)
    assert service.validate_token(raw_secret) is not None

    # Artificially expire the token in database
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    conn = test_db.connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE auth_tokens SET expires_at = ? WHERE id = ?", (past, token.id))
    conn.commit()

    assert service.validate_token(raw_secret) is None


def test_token_scopes_hierarchy() -> None:
    token_read = AuthToken(
        id="tok_1",
        token_prefix="tacp_sec_1234...",
        token_hash="hash1",
        name="Reader",
        scopes=[SCOPE_READ],
        principal_id="p1",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    # tacp.read implies files.read, system.read, process.read
    assert token_read.has_scope(SCOPE_READ)
    assert token_read.has_scope(SCOPE_FILES_READ)
    assert token_read.has_scope(SCOPE_SYSTEM_READ)
    assert token_read.has_scope(SCOPE_PROCESS_READ)
    assert not token_read.has_scope(SCOPE_FILES_WRITE)
    assert not token_read.has_scope(SCOPE_EXECUTE)
    assert not token_read.has_scope(SCOPE_ADMIN)

    token_admin = AuthToken(
        id="tok_2",
        token_prefix="tacp_sec_5678...",
        token_hash="hash2",
        name="Admin",
        scopes=[SCOPE_ADMIN],
        principal_id="p2",
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    # tacp.admin satisfies everything
    assert token_admin.has_scope(SCOPE_READ)
    assert token_admin.has_scope(SCOPE_FILES_READ)
    assert token_admin.has_scope(SCOPE_FILES_WRITE)
    assert token_admin.has_scope(SCOPE_EXECUTE)
    assert token_admin.has_scope(SCOPE_ADMIN)


def test_list_tokens(test_db: Database) -> None:
    service = TokenService(test_db)
    t1, _ = service.create_token("Active 1")
    t2, _ = service.create_token("Active 2")
    t3, _ = service.create_token("Will Revoke")
    service.revoke_token(t3.id)

    active_tokens = service.list_tokens(include_revoked=False)
    assert len(active_tokens) == 2
    assert {t.name for t in active_tokens} == {"Active 1", "Active 2"}

    all_tokens = service.list_tokens(include_revoked=True)
    assert len(all_tokens) == 3


def test_principal_from_token(test_db: Database) -> None:
    service = TokenService(test_db)
    token_agent, _ = service.create_token(
        name="VS Code",
        scopes=[SCOPE_READ, SCOPE_FILES_WRITE, SCOPE_EXECUTE],
    )
    p_agent = service.principal_from_token(token_agent)
    assert p_agent.authenticated is True
    assert p_agent.principal_type == PrincipalType.REMOTE_AI
    assert p_agent.trust_tier == TrustTier.RESTRICTED
    assert Authority.READ_WORKSPACE.value in p_agent.authorities
    assert Authority.MUTATE_WORKSPACE.value in p_agent.authorities
    assert Authority.EXECUTE_COMMAND.value in p_agent.authorities

    token_admin, _ = service.create_token(name="Admin Token", scopes=[SCOPE_ADMIN])
    p_admin = service.principal_from_token(token_admin)
    assert p_admin.role == "admin"
    assert p_admin.trust_tier == TrustTier.PRIVILEGED
    for auth in Authority:
        assert auth.value in p_admin.authorities


def test_invalid_token_inputs(test_db: Database) -> None:
    service = TokenService(test_db)
    with pytest.raises(TacpValidationError):
        service.create_token("   ")

    with pytest.raises(TacpValidationError):
        service.create_token("Test", scopes=["invalid.scope"])

    assert service.validate_token("") is None
    assert service.validate_token("invalid_format_string") is None
    assert service.validate_token("tacp_sec_nonexistent12345678901234567890") is None
