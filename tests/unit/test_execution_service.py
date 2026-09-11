"""Unit tests for ExecutionService (16-stage pipeline, dry-run, approvals, lifecycle)."""

from pathlib import Path

import pytest

from tacp.control.approval import ApprovalEngine
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.execution_service import ExecutionService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import (
    TacpApprovalRequiredError,
    TacpSecurityError,
)
from tacp.domain.execution import ExecutionStatus
from tacp.infrastructure.config import OutputLimits, TacpConfig
from tacp.infrastructure.database import Database


def build_service(
    tmp_path: Path, execution_enabled: bool = True
) -> tuple[ExecutionService, WorkspaceService, ApprovalEngine, str]:
    db = Database(tmp_path / "test_exec_svc.db")
    limits = OutputLimits()
    config = TacpConfig(
        data_dir=tmp_path / "data",
        db_path=tmp_path / "test_exec_svc.db",
        execution_enabled=execution_enabled,
        allowed_workspace_roots=[tmp_path / "workspaces"],
        limits=limits,
    )
    policy_engine = PolicyEngine(execution_enabled=execution_enabled)
    approval_engine = ApprovalEngine(db)
    audit_service = AuditService(db)
    workspace_service = WorkspaceService(db=db)

    ws_root = tmp_path / "workspaces" / "ws-alpha"
    ws_root.mkdir(parents=True, exist_ok=True)
    ws = workspace_service.register_workspace("ws-alpha", ws_root)

    exec_service = ExecutionService(
        db=db,
        config=config,
        policy_engine=policy_engine,
        approval_engine=approval_engine,
        audit_service=audit_service,
        workspace_service=workspace_service,
    )
    return exec_service, workspace_service, approval_engine, ws.id


def test_execution_disabled_by_default(tmp_path: Path) -> None:
    exec_service, _, _, ws_id = build_service(tmp_path, execution_enabled=False)
    with pytest.raises(TacpSecurityError) as exc:
        exec_service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=["printf", "test"],
        )
    assert "disabled" in str(exc.value).lower()


def test_dry_run_evaluation(tmp_path: Path) -> None:
    exec_service, _, _, ws_id = build_service(tmp_path, execution_enabled=True)
    res = exec_service.execute_command(
        workspace_id=ws_id,
        executable="printf",
        argv=["printf", "hello from dry run\n"],
        dry_run=True,
    )
    assert res.status == ExecutionStatus.DRY_RUN.value
    assert res.contract_hash != ""
    assert res.metadata.get("dry_run") is True
    assert "printf" in res.metadata.get("resolved_executable", "")


def test_non_dry_run_requires_approval(tmp_path: Path) -> None:
    exec_service, _, approval_engine, ws_id = build_service(tmp_path, execution_enabled=True)

    # 1. Calling without approval token raises TacpApprovalRequiredError
    with pytest.raises(TacpApprovalRequiredError) as exc:
        exec_service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=["printf", "needs approval\n"],
            dry_run=False,
        )

    ticket_details = exc.value.details
    assert "ticket_id" in ticket_details
    token = ticket_details["token"]
    contract_hash = ticket_details["contract_hash"]
    assert contract_hash

    # 2. Approve ticket
    approval_engine.approve(token, approved_by="human_operator")

    # 3. Execute with approval token
    res = exec_service.execute_command(
        workspace_id=ws_id,
        executable="printf",
        argv=["printf", "needs approval\n"],
        approval_token=token,
        dry_run=False,
    )
    assert res.status == ExecutionStatus.SUCCEEDED.value
    assert res.exit_code == 0
    assert res.stdout == "needs approval\n"

    # 4. Token cannot be reused (replay attack prevented)
    with pytest.raises(TacpSecurityError) as exc2:
        exec_service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=["printf", "needs approval\n"],
            approval_token=token,
            dry_run=False,
        )
    assert "already been consumed" in str(exc2.value).lower()


def test_inspect_and_list_executions(tmp_path: Path) -> None:
    exec_service, _, approval_engine, ws_id = build_service(tmp_path, execution_enabled=True)

    with pytest.raises(TacpApprovalRequiredError) as exc:
        exec_service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=["printf", "logged exec\n"],
            dry_run=False,
        )

    token = exc.value.details["token"]
    approval_engine.approve(token)
    res = exec_service.execute_command(
        workspace_id=ws_id,
        executable="printf",
        argv=["printf", "logged exec\n"],
        approval_token=token,
    )

    # Inspect record
    rec = exec_service.inspect_execution(res.execution_id)
    assert rec is not None
    assert rec["execution_id"] == res.execution_id
    assert rec["status"] == ExecutionStatus.SUCCEEDED.value
    assert rec["exit_code"] == 0

    # List records
    history = exec_service.list_executions(workspace_id=ws_id)
    assert len(history) >= 1
    assert history[0]["execution_id"] == res.execution_id
