import sqlite3
from typing import List, Tuple

MIGRATIONS: List[Tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            root_path TEXT NOT NULL UNIQUE,
            trust_level TEXT NOT NULL DEFAULT 'RESTRICTED',
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            request_id TEXT NOT NULL,
            principal TEXT NOT NULL,
            capability TEXT NOT NULL,
            workspace_id TEXT,
            action TEXT NOT NULL,
            policy_decision TEXT NOT NULL,
            result TEXT NOT NULL,
            duration_ms INTEGER NOT NULL,
            parameters_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs (timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_capability ON audit_logs (capability);
        CREATE INDEX IF NOT EXISTS idx_audit_workspace ON audit_logs (workspace_id);
        CREATE INDEX IF NOT EXISTS idx_workspaces_status ON workspaces (status);
        """,
    ),
]


def apply_migrations(conn: sqlite3.Connection) -> int:
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);"
    )
    conn.commit()

    cursor.execute("SELECT version FROM schema_migrations ORDER BY version ASC;")
    applied = {row[0] for row in cursor.fetchall()}

    applied_count = 0
    for version, sql in MIGRATIONS:
        if version not in applied:
            cursor.executescript(sql)
            cursor.execute(
                """
                INSERT INTO schema_migrations (version, applied_at)
                VALUES (?, CURRENT_TIMESTAMP);
                """,
                (version,),
            )
            conn.commit()
            applied_count += 1

    return applied_count
