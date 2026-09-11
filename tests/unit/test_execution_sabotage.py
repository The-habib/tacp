"""Sabotage and failure injection test suite for TACP Execution Core."""

import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest

from tacp.control.approval import ApprovalEngine
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.execution_service import ExecutionService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import (
    TacpApprovalRequiredError,
    TacpSecurityError,
    TacpValidationError,
)
from tacp.domain.execution import ExecutionStatus
from tacp.infrastructure.config import OutputLimits, TacpConfig
from tacp.infrastructure.database import Database


@pytest.fixture
def sabotage_env(tmp_path: Path) -> Dict[str, Any]:
    db_path = tmp_path / "sabotage_test.db"
    db = Database(db_path)
    limits = OutputLimits(max_execution_duration_seconds=10)
    config = TacpConfig(
        data_dir=tmp_path / "data",
        db_path=db_path,
        execution_enabled=True,
        allowed_workspace_roots=[tmp_path / "workspaces"],
        limits=limits,
    )
    policy_engine = PolicyEngine(execution_enabled=True)
    approval_engine = ApprovalEngine(db)
    audit_service = AuditService(db)
    workspace_service = WorkspaceService(db=db)

    ws_root = tmp_path / "workspaces" / "sabotage-ws"
    ws_root.mkdir(parents=True, exist_ok=True)
    ws = workspace_service.register_workspace("sabotage-ws", ws_root)

    exec_service = ExecutionService(
        db=db,
        config=config,
        policy_engine=policy_engine,
        approval_engine=approval_engine,
        audit_service=audit_service,
        workspace_service=workspace_service,
    )
    return {
        "service": exec_service,
        "ws_id": ws.id,
        "ws_root": ws_root,
        "approval": approval_engine,
        "audit": audit_service,
        "db": db,
        "config": config,
    }


def test_sabotage_ticket_revocation_before_execution(sabotage_env: Dict[str, Any]) -> None:
    """An approved ticket is revoked just prior to execution submission."""
    service: ExecutionService = sabotage_env["service"]
    ws_id: str = sabotage_env["ws_id"]
    approval: ApprovalEngine = sabotage_env["approval"]

    with pytest.raises(TacpApprovalRequiredError) as exc:
        service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=["printf", "revoked test\n"],
            dry_run=False,
        )
    token = exc.value.details["token"]
    approval.approve(token)
    approval.revoke(token, revoked_by="security_officer")

    with pytest.raises(TacpSecurityError) as exc2:
        service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=["printf", "revoked test\n"],
            approval_token=token,
            dry_run=False,
        )
    assert "revoked" in str(exc2.value).lower() or "not approved" in str(exc2.value).lower()


def test_sabotage_workspace_deletion_before_execution(sabotage_env: Dict[str, Any]) -> None:
    """The workspace directory is wiped from the filesystem prior to running."""
    service: ExecutionService = sabotage_env["service"]
    ws_id: str = sabotage_env["ws_id"]
    ws_root: Path = sabotage_env["ws_root"]
    approval: ApprovalEngine = sabotage_env["approval"]

    with pytest.raises(TacpApprovalRequiredError) as exc:
        service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=["printf", "deleted ws test\n"],
            dry_run=False,
        )
    token = exc.value.details["token"]
    approval.approve(token)

    # Delete the workspace root
    ws_root.rmdir()

    with pytest.raises((TacpSecurityError, TacpValidationError)) as exc2:
        service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=["printf", "deleted ws test\n"],
            approval_token=token,
            dry_run=False,
        )
    assert "not exist" in str(exc2.value).lower() or "workspace" in str(exc2.value).lower()


def test_sabotage_concurrent_double_spend_approval_token(sabotage_env: Dict[str, Any]) -> None:
    """Two threads concurrently race to consume the exact same approval token."""
    service: ExecutionService = sabotage_env["service"]
    ws_id: str = sabotage_env["ws_id"]
    approval: ApprovalEngine = sabotage_env["approval"]

    with pytest.raises(TacpApprovalRequiredError) as exc:
        service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=["printf", "double spend\n"],
            dry_run=False,
        )
    token = exc.value.details["token"]
    approval.approve(token)

    results: list[Any] = []
    errors: list[Exception] = []

    def attempt_exec() -> None:
        try:
            r = service.execute_command(
                workspace_id=ws_id,
                executable="printf",
                argv=["printf", "double spend\n"],
                approval_token=token,
                dry_run=False,
            )
            results.append(r)
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=attempt_exec)
    t2 = threading.Thread(target=attempt_exec)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one must succeed, and one must fail with security error
    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], TacpSecurityError)
    assert "consumed" in str(errors[0]).lower() or "not approved" in str(errors[0]).lower()


def test_sabotage_orphan_reconciliation(sabotage_env: Dict[str, Any]) -> None:
    """Simulate a crashed previous daemon leaving a RUNNING execution record in SQLite."""
    service: ExecutionService = sabotage_env["service"]
    ws_id: str = sabotage_env["ws_id"]
    db: Database = sabotage_env["db"]

    orphan_id = "exec-orphan-deadbeef"
    # Insert an orphan record directly into executions table
    conn = db.connect()
    with conn:
        conn.execute(
            """
            INSERT INTO executions (
                id, execution_id, action_type, workspace_id, executable, argv_json,
                cwd, contract_hash, principal_id, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                orphan_id,
                orphan_id,
                "execution.request",
                ws_id,
                "/bin/printf",
                '["printf", "orphan"]',
                "/tmp",
                "fake_hash_orphan",
                "test_principal",
                ExecutionStatus.RUNNING.value,
            ),
        )

    # Reconcile orphans
    reconciled_count = service.reconcile_orphans()
    assert reconciled_count >= 1

    # Status must now be FAILED or ORPHANED
    record = service.inspect_execution(orphan_id)
    assert record is not None
    assert record["status"] in (ExecutionStatus.FAILED.value, ExecutionStatus.ORPHANED.value)


def test_sabotage_database_write_failure_during_completion(sabotage_env: Dict[str, Any]) -> None:
    """Simulate a database failure when updating execution completion status."""
    service: ExecutionService = sabotage_env["service"]
    ws_id: str = sabotage_env["ws_id"]
    approval: ApprovalEngine = sabotage_env["approval"]
    db: Database = sabotage_env["db"]

    with pytest.raises(TacpApprovalRequiredError) as exc:
        service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=["printf", "db failure test\n"],
            dry_run=False,
        )
    token = exc.value.details["token"]
    approval.approve(token)

    orig_conn = db.connect()

    class SabotageConnectionWrapper:
        def __init__(self, real_conn: Any):
            self._real = real_conn

        def execute(self, sql: str, *args: Any, **kwargs: Any) -> Any:
            if "UPDATE executions" in sql:
                raise sqlite3.OperationalError("disk I/O error (sabotage simulation)")
            return self._real.execute(sql, *args, **kwargs)

        def cursor(self) -> Any:
            return self._real.cursor()

        def commit(self) -> None:
            self._real.commit()

        def rollback(self) -> None:
            self._real.rollback()

        def __enter__(self) -> Any:
            return self

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
            return False

        def __getattr__(self, name: str) -> Any:
            return getattr(self._real, name)

    with patch.object(db, "connect", return_value=SabotageConnectionWrapper(orig_conn)):
        with pytest.raises(sqlite3.OperationalError):
            service.execute_command(
                workspace_id=ws_id,
                executable="printf",
                argv=["printf", "db failure test\n"],
                approval_token=token,
                dry_run=False,
            )
