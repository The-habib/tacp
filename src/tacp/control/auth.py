"""Authentication and Token Management for TACP."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from tacp.control.identity import Authority, CredentialSource, Principal, PrincipalType, TrustTier
from tacp.domain.errors import TacpValidationError
from tacp.infrastructure.database import Database

SCOPE_READ = "tacp.read"
SCOPE_FILES_READ = "tacp.files.read"
SCOPE_FILES_WRITE = "tacp.files.write"
SCOPE_SYSTEM_READ = "tacp.system.read"
SCOPE_PROCESS_READ = "tacp.process.read"
SCOPE_EXECUTE = "tacp.execute"
SCOPE_ADMIN = "tacp.admin"

VALID_SCOPES: Set[str] = {
    SCOPE_READ,
    SCOPE_FILES_READ,
    SCOPE_FILES_WRITE,
    SCOPE_SYSTEM_READ,
    SCOPE_PROCESS_READ,
    SCOPE_EXECUTE,
    SCOPE_ADMIN,
}

DEFAULT_SCOPES: List[str] = [SCOPE_READ]


@dataclass(frozen=True)
class AuthToken:
    """Represents a stored authentication token record."""

    id: str
    token_prefix: str
    token_hash: str
    name: str
    scopes: List[str]
    principal_id: str
    created_at: str
    expires_at: Optional[str] = None
    last_used_at: Optional[str] = None
    revoked: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            exp = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) > exp
        except Exception:
            return True

    def is_valid(self) -> bool:
        return not self.revoked and not self.is_expired()

    def has_scope(self, scope: str) -> bool:
        if SCOPE_ADMIN in self.scopes:
            return True
        if scope in self.scopes:
            return True
        if (
            scope in (SCOPE_FILES_READ, SCOPE_SYSTEM_READ, SCOPE_PROCESS_READ)
            and SCOPE_READ in self.scopes
        ):
            return True
        return False

    def to_dict(self, include_hash: bool = False) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": self.id,
            "token_prefix": self.token_prefix,
            "name": self.name,
            "scopes": self.scopes,
            "principal_id": self.principal_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "last_used_at": self.last_used_at,
            "revoked": self.revoked,
            "metadata": self.metadata,
        }
        if include_hash:
            data["token_hash"] = self.token_hash
        return data


def hash_token(raw_token: str) -> str:
    """Compute SHA-256 hash of a bearer token."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


class TokenService:
    """Manages creation, verification, and revocation of bearer tokens."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self._cache: Dict[str, Tuple[AuthToken, float]] = {}
        self._last_touch: Dict[str, float] = {}
        self._last_changes: Optional[int] = None
        self._cache_ttl: float = 30.0

    def clear_cache(self) -> None:
        """Clear the in-memory token validation cache."""
        self._cache.clear()

    def create_token(
        self,
        name: str,
        scopes: Optional[List[str]] = None,
        principal_id: Optional[str] = None,
        expires_days: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> tuple[AuthToken, str]:
        """Generate a cryptographically secure token and persist its hash."""
        clean_name = name.strip()
        if not clean_name:
            raise TacpValidationError("Token name cannot be empty.")

        requested_scopes = scopes or DEFAULT_SCOPES
        for sc in requested_scopes:
            if sc not in VALID_SCOPES:
                raise TacpValidationError(f"Invalid token scope: {sc}")

        token_id = f"tok_{uuid.uuid4().hex[:12]}"
        raw_secret = f"tacp_sec_{secrets.token_hex(32)}"
        token_hash = hash_token(raw_secret)
        prefix = raw_secret[:16] + "..."

        now = datetime.now(timezone.utc)
        created_at = now.isoformat()
        expires_at = (now + timedelta(days=expires_days)).isoformat() if expires_days else None
        p_id = principal_id or f"remote_{clean_name.lower().replace(' ', '_')}"

        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO auth_tokens (
                id, token_prefix, token_hash, name, scopes_json,
                principal_id, created_at, expires_at, revoked, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?);
            """,
            (
                token_id,
                prefix,
                token_hash,
                clean_name,
                json.dumps(requested_scopes),
                p_id,
                created_at,
                expires_at,
                json.dumps(metadata or {}),
            ),
        )
        conn.commit()

        token_record = AuthToken(
            id=token_id,
            token_prefix=prefix,
            token_hash=token_hash,
            name=clean_name,
            scopes=requested_scopes,
            principal_id=p_id,
            created_at=created_at,
            expires_at=expires_at,
            revoked=False,
            metadata=metadata or {},
        )
        return token_record, raw_secret

    def validate_token(self, raw_token: str) -> Optional[AuthToken]:
        """Validate a plaintext token against stored hashes and check validity."""
        if not raw_token or not isinstance(raw_token, str):
            return None

        clean_token = raw_token.strip()
        if clean_token.startswith("Bearer "):
            clean_token = clean_token[7:].strip()

        if not clean_token.startswith("tacp_sec_"):
            return None

        token_hash = hash_token(clean_token)
        now = time.time()
        conn = self.db.connect()
        changes = getattr(conn, "total_changes", None)
        if self._last_changes is not None and changes is not None and changes != self._last_changes:
            self._cache.clear()
        self._last_changes = changes

        if token_hash in self._cache:
            cached_rec, cached_at = self._cache[token_hash]
            if (now - cached_at < self._cache_ttl) and cached_rec.is_valid():
                return cached_rec

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, token_prefix, token_hash, name, scopes_json,
                   principal_id, created_at, expires_at, last_used_at,
                   revoked, metadata_json
            FROM auth_tokens
            WHERE token_hash = ?;
            """,
            (token_hash,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        record = AuthToken(
            id=row["id"],
            token_prefix=row["token_prefix"],
            token_hash=row["token_hash"],
            name=row["name"],
            scopes=json.loads(row["scopes_json"]),
            principal_id=row["principal_id"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            last_used_at=row["last_used_at"],
            revoked=bool(row["revoked"]),
            metadata=json.loads(row["metadata_json"]),
        )

        if not record.is_valid():
            return None

        self._cache[token_hash] = (record, now)

        # Update last_used_at timestamp throttled to at most once per 60s
        if now - self._last_touch.get(record.id, 0.0) >= 60.0:
            self._last_touch[record.id] = now
            now_str = datetime.now(timezone.utc).isoformat()
            try:
                cursor.execute(
                    "UPDATE auth_tokens SET last_used_at = ? WHERE id = ?;",
                    (now_str, record.id),
                )
                conn.commit()
                self._last_changes = getattr(conn, "total_changes", None)
            except Exception:
                pass

        return record

    def list_tokens(self, include_revoked: bool = False) -> List[AuthToken]:
        """List all authentication tokens."""
        conn = self.db.connect()
        cursor = conn.cursor()
        if include_revoked:
            cursor.execute(
                """
                SELECT id, token_prefix, token_hash, name, scopes_json,
                       principal_id, created_at, expires_at, last_used_at,
                       revoked, metadata_json
                FROM auth_tokens
                ORDER BY created_at DESC;
                """
            )
        else:
            cursor.execute(
                """
                SELECT id, token_prefix, token_hash, name, scopes_json,
                       principal_id, created_at, expires_at, last_used_at,
                       revoked, metadata_json
                FROM auth_tokens
                WHERE revoked = 0
                ORDER BY created_at DESC;
                """
            )
        rows = cursor.fetchall()
        tokens = []
        for r in rows:
            tokens.append(
                AuthToken(
                    id=r["id"],
                    token_prefix=r["token_prefix"],
                    token_hash=r["token_hash"],
                    name=r["name"],
                    scopes=json.loads(r["scopes_json"]),
                    principal_id=r["principal_id"],
                    created_at=r["created_at"],
                    expires_at=r["expires_at"],
                    last_used_at=r["last_used_at"],
                    revoked=bool(r["revoked"]),
                    metadata=json.loads(r["metadata_json"]),
                )
            )
        return tokens

    def revoke_token(self, token_id: str) -> bool:
        """Revoke a token by ID."""
        self._cache.clear()
        conn = self.db.connect()
        cursor = conn.cursor()
        cursor.execute("UPDATE auth_tokens SET revoked = 1 WHERE id = ?;", (token_id,))
        conn.commit()
        return cursor.rowcount > 0

    def principal_from_token(self, token: AuthToken) -> Principal:
        """Convert an authenticated token into a security Principal with appropriate authorities."""
        authorities: Set[str] = set()

        if token.has_scope(SCOPE_READ) or token.has_scope(SCOPE_FILES_READ):
            authorities.add(Authority.READ_WORKSPACE.value)
            authorities.add(Authority.VIEW_AUDIT.value)

        if token.has_scope(SCOPE_FILES_WRITE):
            authorities.add(Authority.MUTATE_WORKSPACE.value)

        if token.has_scope(SCOPE_EXECUTE):
            authorities.add(Authority.EXECUTE_COMMAND.value)

        if token.has_scope(SCOPE_ADMIN):
            for a in Authority:
                authorities.add(a.value)

        tier = TrustTier.PRIVILEGED if token.has_scope(SCOPE_ADMIN) else TrustTier.RESTRICTED

        return Principal(
            id=token.principal_id,
            role="agent" if not token.has_scope(SCOPE_ADMIN) else "admin",
            authenticated=True,
            principal_type=PrincipalType.REMOTE_AI,
            trust_tier=tier,
            credential_source=CredentialSource.TOKEN,
            authorities=frozenset(authorities),
            metadata={"token_id": token.id, "token_name": token.name, "scopes": token.scopes},
        )
