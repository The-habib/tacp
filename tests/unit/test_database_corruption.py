"""Tests for Database Corruption and Failure Injection (Section 29)."""

import sqlite3
from pathlib import Path

import pytest

from tacp.core.audit_service import AuditService
from tacp.infrastructure.database import Database


def test_database_is_healthy_on_valid_db(tmp_path: Path) -> None:
    db_path = tmp_path / "healthy.db"
    db = Database(db_path)
    assert db.is_healthy() is True
    db.close()


def test_database_is_healthy_false_on_corrupt_file(tmp_path: Path) -> None:
    db_path = tmp_path / "corrupt.db"
    # Create valid db first
    db = Database(db_path)
    assert db.is_healthy() is True
    db.close()

    # Corrupt the SQLite header
    with open(db_path, "r+b") as f:
        f.seek(0)
        f.write(b"NOT_A_SQLITE_DATABASE_CORRUPT_HEADER_BYTES_1234567890\x00\xff")

    # Now verify is_healthy returns False safely without crashing
    corrupt_db = Database(db_path)
    assert corrupt_db.is_healthy() is False
    corrupt_db.close()


def test_service_operation_on_corrupt_db_fails_safely(tmp_path: Path) -> None:
    db_path = tmp_path / "corrupt_service.db"
    db = Database(db_path)
    assert db.is_healthy() is True

    # Corrupt DB file
    db.close()
    with open(db_path, "wb") as f:
        f.write(b"GARBAGE_PAYLOAD" * 50)

    # Attempting to query or record on corrupt DB raises sqlite3.DatabaseError or fails safely
    corrupt_db = Database(db_path)
    corrupt_service = AuditService(corrupt_db)

    with pytest.raises((sqlite3.DatabaseError, sqlite3.OperationalError)):
        corrupt_service.get_recent_events()

    corrupt_db.close()


def test_database_recreates_parent_directory_if_missing(tmp_path: Path) -> None:
    nested_dir = tmp_path / "nested" / "sub" / "folder"
    db_path = nested_dir / "tacp.db"
    assert not nested_dir.exists()

    db = Database(db_path)
    assert db.is_healthy() is True
    assert db_path.exists()
    db.close()
