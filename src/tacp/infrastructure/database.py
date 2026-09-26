import sqlite3
import threading
from pathlib import Path
from typing import Optional

from tacp.infrastructure.migrations import apply_migrations


class Database:
    _migrated_paths: set = set()
    _migration_lock = threading.Lock()

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._local = threading.local()

    def connect(self) -> sqlite3.Connection:
        conn: Optional[sqlite3.Connection] = getattr(self._local, "conn", None)
        if conn is None:
            if not self.db_path.parent.exists():
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            # WAL mode and foreign key enforcement
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")

            # Only run migrations once per database path
            path_key = str(self.db_path.resolve())
            if path_key not in Database._migrated_paths:
                with Database._migration_lock:
                    if path_key not in Database._migrated_paths:
                        apply_migrations(conn)
                        Database._migrated_paths.add(path_key)

            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn: Optional[sqlite3.Connection] = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def is_healthy(self) -> bool:
        try:
            conn = self.connect()
            cursor = conn.cursor()
            cursor.execute("SELECT 1;")
            row = cursor.fetchone()
            return row is not None and row[0] == 1
        except Exception:
            return False
