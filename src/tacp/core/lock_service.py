import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Generator, Optional

from tacp.domain.errors import (
    TacpConflictError,
)
from tacp.infrastructure.database import Database

logger = logging.getLogger(__name__)


class LockService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def acquire_lock(
        self,
        resource_id: str,
        owner_id: str,
        ttl_seconds: int = 30,
    ) -> str:
        """Acquire an exclusive lock atomically using SQLite BEGIN IMMEDIATE and INSERT.

        Guarantees that concurrent processes/threads cannot both acquire the same
        resource even under high contention.
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        token = f"tacp_lock_{uuid.uuid4().hex}"
        acquired_at = now_iso
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()

        conn = self.db.connect()
        # BEGIN IMMEDIATE acquires a reserved write lock immediately
        conn.execute("BEGIN IMMEDIATE;")
        cur = conn.cursor()
        try:
            # 1. Atomically purge expired lock for this resource
            cur.execute(
                "DELETE FROM locks WHERE resource_id = ? AND expires_at <= ?;",
                (resource_id, now_iso),
            )

            # 2. Attempt atomic insertion (resource_id is PRIMARY KEY)
            cur.execute(
                """
                INSERT INTO locks (
                    resource_id, owner_id, acquired_at, expires_at, token
                ) VALUES (?, ?, ?, ?, ?);
                """,
                (resource_id, owner_id, acquired_at, expires_at, token),
            )
            conn.commit()
            return token
        except sqlite3.IntegrityError as err:
            conn.rollback()
            # Active, unexpired lock exists — query details for descriptive error
            cur.execute(
                "SELECT owner_id, expires_at FROM locks WHERE resource_id = ?;",
                (resource_id,),
            )
            existing = cur.fetchone()
            if existing:
                raise TacpConflictError(
                    f"Resource '{resource_id}' is locked by '{existing[0]}' until {existing[1]}"
                ) from err
            # Edge-case fallback: lock was released between insert and rollback
            raise TacpConflictError(f"Resource '{resource_id}' is currently locked") from err
        except Exception:
            conn.rollback()
            raise

    def release_lock(
        self,
        resource_id: str,
        token: str,
        owner_id: Optional[str] = None,
    ) -> bool:
        """Release a lock only if token matches and owner_id matches (if provided).

        Prevents previous owners with stale tokens or foreign owners from releasing
        another owner's active lock.
        """
        conn = self.db.connect()
        with conn:
            cur = conn.cursor()
            if owner_id:
                cur.execute(
                    "DELETE FROM locks WHERE resource_id = ? AND token = ? AND owner_id = ?;",
                    (resource_id, token, owner_id),
                )
            else:
                cur.execute(
                    "DELETE FROM locks WHERE resource_id = ? AND token = ?;",
                    (resource_id, token),
                )
            return cur.rowcount > 0

    def refresh_lock(
        self,
        resource_id: str,
        token: str,
        owner_id: str,
        additional_seconds: int = 30,
    ) -> bool:
        """Extend lock lease TTL before expiration if still held by the owner."""
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        new_expires_at = (now + timedelta(seconds=additional_seconds)).isoformat()
        conn = self.db.connect()
        with conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE locks
                SET expires_at = ?
                WHERE resource_id = ? AND token = ? AND owner_id = ? AND expires_at > ?;
                """,
                (new_expires_at, resource_id, token, owner_id, now_iso),
            )
            return cur.rowcount > 0

    @contextmanager
    def hold(
        self,
        resource_id: str,
        owner_id: str,
        ttl_seconds: int = 30,
    ) -> Generator[str, None, None]:
        token = self.acquire_lock(resource_id, owner_id, ttl_seconds)
        try:
            yield token
        finally:
            self.release_lock(resource_id, token, owner_id=owner_id)

    def release_many(self, locks: dict[str, str], owner_id: Optional[str] = None) -> None:
        for rid, token in reversed(list(locks.items())):
            try:
                self.release_lock(rid, token, owner_id=owner_id)
            except Exception as exc:
                logger.debug("Failed to release lock %s: %s", rid, exc)

    @contextmanager
    def hold_many(
        self,
        resource_ids: list[str],
        owner_id: str,
        ttl_seconds: int = 45,
    ) -> Generator[dict[str, str], None, None]:
        # Sort lexicographically to guarantee deterministic global lock acquisition order
        sorted_ids = sorted(resource_ids)
        acquired: dict[str, str] = {}
        try:
            for rid in sorted_ids:
                token = self.acquire_lock(rid, owner_id, ttl_seconds)
                acquired[rid] = token
            yield acquired
        finally:
            self.release_many(acquired, owner_id=owner_id)
