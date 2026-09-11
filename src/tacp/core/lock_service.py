from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Generator

from tacp.domain.errors import (
    TacpConflictError,
)
from tacp.infrastructure.database import Database


class LockService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def acquire_lock(
        self,
        resource_id: str,
        owner_id: str,
        ttl_seconds: int = 30,
    ) -> str:
        now = datetime.now(timezone.utc)
        conn = self.db.connect()
        cur = conn.cursor()

        # Check existing lock
        cur.execute(
            """
            SELECT resource_id, owner_id, acquired_at, expires_at, token
            FROM locks WHERE resource_id = ?;
            """,
            (resource_id,),
        )
        row = cur.fetchone()
        if row:
            existing_owner = row[1]
            existing_expires = datetime.fromisoformat(row[3])
            if now < existing_expires:
                raise TacpConflictError(
                    f"Resource '{resource_id}' is locked by '{existing_owner}' until {row[3]}"
                )
            else:
                # Expired lock can be purged
                cur.execute("DELETE FROM locks WHERE resource_id = ?;", (resource_id,))

        token = f"tacp_lock_{uuid.uuid4().hex}"
        acquired_at = now.isoformat()
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()

        cur.execute(
            """
            INSERT OR REPLACE INTO locks (
                resource_id, owner_id, acquired_at, expires_at, token
            ) VALUES (?, ?, ?, ?, ?);
            """,
            (resource_id, owner_id, acquired_at, expires_at, token),
        )
        conn.commit()
        return token

    def release_lock(self, resource_id: str, token: str) -> bool:
        conn = self.db.connect()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM locks WHERE resource_id = ? AND token = ?;",
            (resource_id, token),
        )
        conn.commit()
        deleted = cur.rowcount > 0
        return deleted

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
            self.release_lock(resource_id, token)
