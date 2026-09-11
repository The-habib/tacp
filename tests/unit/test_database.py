"""Tests for SQLite Database, Migrations, and Workspaces (Category J)."""

from pathlib import Path

import pytest

from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import TacpNotFoundError, TacpValidationError
from tacp.infrastructure.database import Database
from tacp.infrastructure.migrations import apply_migrations


def test_db_wal_mode_enabled(test_db: Database) -> None:
    conn = test_db.connect()
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    mode = cursor.fetchone()[0]
    assert mode.upper() == "WAL"


def test_db_foreign_keys_enabled(test_db: Database) -> None:
    conn = test_db.connect()
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys;")
    val = cursor.fetchone()[0]
    assert val == 1


def test_migrations_are_idempotent(test_db: Database) -> None:
    conn = test_db.connect()
    # Re-running migrations should return 0 new migrations
    count = apply_migrations(conn)
    assert count == 0


def test_schema_tables_created(test_db: Database) -> None:
    conn = test_db.connect()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {r[0] for r in cursor.fetchall()}
    assert "schema_migrations" in tables
    assert "workspaces" in tables
    assert "audit_logs" in tables


def test_schema_indexes_created(test_db: Database) -> None:
    conn = test_db.connect()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
    indexes = {r[0] for r in cursor.fetchall()}
    assert "idx_audit_timestamp" in indexes
    assert "idx_audit_capability" in indexes
    assert "idx_workspaces_status" in indexes


def test_database_is_healthy(test_db: Database) -> None:
    assert test_db.is_healthy() is True


def test_workspace_service_registration(test_db: Database, tmp_path: Path) -> None:
    service = WorkspaceService(test_db)
    ws_dir = tmp_path / "my_ws"
    ws_dir.mkdir()

    ws = service.register_workspace("my_ws", ws_dir)
    assert ws.name == "my_ws"
    assert ws.root_path == ws_dir.resolve()
    assert ws.status == "ACTIVE"

    listed = service.list_workspaces()
    assert len(listed) >= 1
    assert any(w["name"] == "my_ws" for w in listed)


def test_workspace_service_get_by_id_and_name(test_db: Database, tmp_path: Path) -> None:
    service = WorkspaceService(test_db)
    ws_dir = tmp_path / "ws_lookup"
    ws_dir.mkdir()

    ws = service.register_workspace("lookup_ws", ws_dir)
    by_id = service.get_workspace(ws.id)
    assert by_id.id == ws.id

    by_name = service.get_workspace("lookup_ws")
    assert by_name.id == ws.id


def test_workspace_service_not_found(test_db: Database) -> None:
    service = WorkspaceService(test_db)
    with pytest.raises(TacpNotFoundError):
        service.get_workspace("nonexistent-workspace-id")


def test_workspace_registration_fails_on_nonexistent_dir(test_db: Database, tmp_path: Path) -> None:
    service = WorkspaceService(test_db)
    with pytest.raises(TacpValidationError):
        service.register_workspace("fake", tmp_path / "does_not_exist")


def test_workspace_service_inspect(test_db: Database, tmp_path: Path) -> None:
    service = WorkspaceService(test_db)
    ws_dir = tmp_path / "inspectable_ws"
    ws_dir.mkdir()
    (ws_dir / "file1.txt").write_text("12345")

    ws = service.register_workspace("inspectable", ws_dir)
    inspection = service.inspect_workspace(ws.id)

    assert inspection["workspace"]["id"] == ws.id
    assert inspection["summary"]["file_count"] == 1
    assert inspection["summary"]["total_bytes"] == 5
