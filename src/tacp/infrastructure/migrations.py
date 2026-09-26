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
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS principals (
            id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            trust_tier TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS policies (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            rules_json TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 100,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY,
            token TEXT NOT NULL UNIQUE,
            action_type TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            target_path TEXT NOT NULL,
            patch_hash TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            consumed_at TEXT,
            consumed_by TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS patches (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            target_path TEXT NOT NULL,
            base_checksum TEXT NOT NULL,
            result_checksum TEXT NOT NULL,
            diff_content TEXT NOT NULL,
            status TEXT NOT NULL,
            snapshot_path TEXT,
            applied_at TEXT NOT NULL,
            applied_by TEXT NOT NULL,
            rollback_at TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS locks (
            resource_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            acquired_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE
        );

        CREATE INDEX IF NOT EXISTS idx_approvals_token ON approvals (token);
        CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals (status);
        CREATE INDEX IF NOT EXISTS idx_patches_workspace ON patches (workspace_id);
        CREATE INDEX IF NOT EXISTS idx_locks_expires ON locks (expires_at);
        """,
    ),
    (
        3,
        """
        CREATE TABLE IF NOT EXISTS batches (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            batch_hash TEXT NOT NULL,
            patch_count INTEGER NOT NULL,
            status TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            applied_by TEXT NOT NULL,
            rollback_at TEXT,
            snapshot_manifest_json TEXT NOT NULL DEFAULT '{}',
            results_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_batches_workspace ON batches (workspace_id);
        """,
    ),
    (
        4,
        """
        ALTER TABLE approvals ADD COLUMN token_hash TEXT;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_approvals_token_hash ON approvals (token_hash);
        """,
    ),
    (
        5,
        """
        ALTER TABLE audit_logs ADD COLUMN prev_hash TEXT;
        ALTER TABLE audit_logs ADD COLUMN entry_hash TEXT;
        CREATE INDEX IF NOT EXISTS idx_audit_entry_hash ON audit_logs (entry_hash);
        """,
    ),
    (
        6,
        """
        CREATE TABLE IF NOT EXISTS executions (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL UNIQUE,
            action_type TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            executable TEXT NOT NULL,
            argv_json TEXT NOT NULL,
            cwd TEXT NOT NULL,
            contract_hash TEXT NOT NULL,
            principal_id TEXT NOT NULL,
            status TEXT NOT NULL,
            exit_code INTEGER,
            term_signal INTEGER,
            duration_ms INTEGER,
            stdout_truncated INTEGER NOT NULL DEFAULT 0,
            stderr_truncated INTEGER NOT NULL DEFAULT 0,
            timed_out INTEGER NOT NULL DEFAULT 0,
            cancelled INTEGER NOT NULL DEFAULT 0,
            pid INTEGER,
            pgid INTEGER,
            created_at TEXT NOT NULL,
            started_at TEXT,
            terminated_at TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_executions_workspace ON executions (workspace_id);
        CREATE INDEX IF NOT EXISTS idx_executions_status ON executions (status);
        CREATE INDEX IF NOT EXISTS idx_executions_contract_hash ON executions (contract_hash);
        """,
    ),
    (
        7,
        """
        CREATE TABLE IF NOT EXISTS leases (
            id TEXT PRIMARY KEY,
            lease_id TEXT NOT NULL UNIQUE,
            principal_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            capabilities_json TEXT NOT NULL DEFAULT '[]',
            resources_json TEXT NOT NULL DEFAULT '[]',
            risk_ceiling TEXT NOT NULL DEFAULT 'R2',
            budget INTEGER NOT NULL DEFAULT 1,
            budget_remaining INTEGER NOT NULL DEFAULT 1,
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            trust_profile TEXT NOT NULL DEFAULT 'BALANCED',
            policy_version INTEGER NOT NULL DEFAULT 1,
            session_id TEXT,
            revoked INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_leases_lookup
            ON leases (lease_id, principal_id, workspace_id);
        CREATE INDEX IF NOT EXISTS idx_leases_expires ON leases (expires_at);
        """,
    ),
    (
        8,
        """
        CREATE TABLE IF NOT EXISTS auth_tokens (
            id TEXT PRIMARY KEY,
            token_prefix TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            scopes_json TEXT NOT NULL DEFAULT '["tacp.read"]',
            principal_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            last_used_at TEXT,
            revoked INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_auth_tokens_hash ON auth_tokens (token_hash);
        CREATE INDEX IF NOT EXISTS idx_auth_tokens_revoked ON auth_tokens (revoked);

        CREATE TABLE IF NOT EXISTS device_pairing (
            id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL UNIQUE,
            device_name TEXT NOT NULL,
            pairing_code TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            paired_at TEXT,
            paired_principal TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_device_pairing_code ON device_pairing (pairing_code);
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
