"""Chaos Fault Injection Suite for TACP Phase 3."""

import os
import sqlite3
import threading
import time
import pytest
from pathlib import Path
from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import create_mcp_server
from tacp.backends.companion_transport import HttpCompanionTransport, CircuitState
from tacp.control.identity import RequestContext
from tacp.core.audit_service import AuditService
from tacp.domain.audit import AuditEvent
from tacp.domain.errors import ErrorCode, TacpError
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database


def test_chaos_database_busy_recovery(tmp_path):
    """Simulate concurrent transaction lock contention and verify 30s busy timeout handles it cleanly."""
    db_path = tmp_path / "busy_chaos.db"
    db = Database(db_path)
    db.connect()
    audit_svc = AuditService(db)

    ready_evt = threading.Event()

    def lock_and_release():
        conn_ext = sqlite3.connect(str(db_path), timeout=0.1, check_same_thread=False)
        conn_ext.execute("BEGIN EXCLUSIVE;")
        ready_evt.set()
        time.sleep(0.15)
        conn_ext.commit()
        conn_ext.close()

    t = threading.Thread(target=lock_and_release)
    t.start()
    ready_evt.wait()

    # Audit write waits for busy timeout, acquires lock, and succeeds!
    evt = AuditEvent(
        capability="system.health",
        action="health",
        policy_decision="ALLOWED",
        result="SUCCESS",
        duration_ms=1,
    )
    entry_hash = audit_svc.record_event(evt)
    t.join()
    assert entry_hash is not None
    assert len(entry_hash) == 64


def test_chaos_corrupted_database_detection(tmp_path):
    """Simulate raw physical corruption of SQLite database file."""
    db_path = tmp_path / "corrupt.db"
    db = Database(db_path)
    db.connect()

    db.close()
    # Corrupt the header bytes
    with open(db_path, "r+b") as f:
        f.seek(0)
        f.write(b"CORRUPTED_GARBAGE_HEADER_DATA_NOT_SQLITE")

    # Healthy check must return False
    assert not db.is_healthy()


def test_chaos_companion_disconnection_resilience():
    """Verify circuit breaker trips and fails fast without blocking control plane."""
    transport = HttpCompanionTransport(port=59996, failure_threshold=2, recovery_timeout=0.2)
    
    # 2 failures trip circuit
    for _ in range(2):
        with pytest.raises(TacpError):
            transport.send_request("/ping", timeout=0.02)

    assert transport.circuit_state == CircuitState.OPEN
    t0 = time.perf_counter()
    with pytest.raises(TacpError) as exc_info:
        transport.send_request("/ping")
    fail_fast_time = (time.perf_counter() - t0) * 1000.0

    assert exc_info.value.code == ErrorCode.UNAVAILABLE
    assert fail_fast_time < 0.5 # < 0.5ms fail fast


def test_chaos_cancellation_propagation():
    """Verify deadline propagation cleanly aborts in-flight operation."""
    ctx = RequestContext(
        capability="execution.request",
        deadline_monotonic=time.monotonic() - 0.01,
    )
    with pytest.raises(TacpError) as exc_info:
        ctx.check_cancelled()
    assert exc_info.value.code == ErrorCode.DEADLINE_EXCEEDED
