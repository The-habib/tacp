import sqlite3
from pathlib import Path
from typing import Optional

from tacp.infrastructure.migrations import apply_migrations


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            if not self.db_path.parent.exists():
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self.db_path),
                timeout=10.0,
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            # WAL mode and foreign key enforcement
            self._conn.execute("PRAGMA journal_mode = WAL;")
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.execute("PRAGMA synchronous = NORMAL;")
            apply_migrations(self._conn)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def is_healthy(self) -> bool:
        try:
            conn = self.connect()
            cursor = conn.cursor()
            cursor.execute("SELECT 1;")
            row = cursor.fetchone()
            return row is not None and row[0] == 1
        except Exception:
            return False
