"""On-device physical execution verification tests for Termux/Android/Linux."""

from pathlib import Path
from typing import Any, Dict

import pytest

from tacp.control.approval import ApprovalEngine
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.execution_resolver import ExecutionResolver
from tacp.core.execution_service import ExecutionService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import TacpApprovalRequiredError, TacpSecurityError
from tacp.domain.execution import ExecutionStatus
from tacp.infrastructure.config import OutputLimits, TacpConfig
from tacp.infrastructure.database import Database

pytestmark = pytest.mark.device


@pytest.fixture
def device_exec_env(tmp_path: Path) -> Dict[str, Any]:
    db_path = tmp_path / "termux_device_exec.db"
    db = Database(db_path)
    limits = OutputLimits()
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

    ws_root = tmp_path / "workspaces" / "device-ws"
    ws_root.mkdir(parents=True, exist_ok=True)
    ws = workspace_service.register_workspace("device-ws", ws_root)

    service = ExecutionService(
        db=db,
        config=config,
        policy_engine=policy_engine,
        approval_engine=approval_engine,
        audit_service=audit_service,
        workspace_service=workspace_service,
    )
    return {
        "service": service,
        "ws_id": ws.id,
        "ws_root": ws_root,
        "approval": approval_engine,
        "audit": audit_service,
        "config": config,
    }


def test_device_printf_live_execution(device_exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = device_exec_env["service"]
    ws_id: str = device_exec_env["ws_id"]
    approval: ApprovalEngine = device_exec_env["approval"]

    # 1. Approval required
    with pytest.raises(TacpApprovalRequiredError) as exc:
        service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=["printf", "TACP_TERMUX_DEVICE_OK\n"],
            dry_run=False,
        )
    token = exc.value.details["token"]
    approval.approve(token)

    # 2. Live execution
    res = service.execute_command(
        workspace_id=ws_id,
        executable="printf",
        argv=["printf", "TACP_TERMUX_DEVICE_OK\n"],
        approval_token=token,
        dry_run=False,
    )
    assert res.status == ExecutionStatus.SUCCEEDED.value
    assert res.exit_code == 0
    assert res.stdout == "TACP_TERMUX_DEVICE_OK\n"
    assert res.duration_ms >= 0


def test_device_echo_live_execution(device_exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = device_exec_env["service"]
    ws_id: str = device_exec_env["ws_id"]
    approval: ApprovalEngine = device_exec_env["approval"]

    with pytest.raises(TacpApprovalRequiredError) as exc:
        service.execute_command(
            workspace_id=ws_id,
            executable="echo",
            argv=["echo", "LIVE_ON_ANDROID"],
            dry_run=False,
        )
    token = exc.value.details["token"]
    approval.approve(token)

    res = service.execute_command(
        workspace_id=ws_id,
        executable="echo",
        argv=["echo", "LIVE_ON_ANDROID"],
        approval_token=token,
        dry_run=False,
    )
    assert res.status == ExecutionStatus.SUCCEEDED.value
    assert res.exit_code == 0
    assert "LIVE_ON_ANDROID" in res.stdout


def test_device_true_live_execution(device_exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = device_exec_env["service"]
    ws_id: str = device_exec_env["ws_id"]
    approval: ApprovalEngine = device_exec_env["approval"]

    with pytest.raises(TacpApprovalRequiredError) as exc:
        service.execute_command(
            workspace_id=ws_id,
            executable="true",
            argv=["true"],
            dry_run=False,
        )
    token = exc.value.details["token"]
    approval.approve(token)

    res = service.execute_command(
        workspace_id=ws_id,
        executable="true",
        argv=["true"],
        approval_token=token,
        dry_run=False,
    )
    assert res.status == ExecutionStatus.SUCCEEDED.value
    assert res.exit_code == 0
    assert res.stdout == ""


def test_device_disallowed_shell_binaries_rejected(device_exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = device_exec_env["service"]
    ws_id: str = device_exec_env["ws_id"]

    for forbidden in ["sh", "bash", "python", "python3", "cat", "ls"]:
        with pytest.raises(TacpSecurityError) as exc:
            service.execute_command(
                workspace_id=ws_id,
                executable=forbidden,
                argv=[forbidden, "-c", "whoami"],
                dry_run=True,
            )
        err = str(exc.value).lower()
        assert "forbidden" in err or "whitelist" in err or "not permitted" in err


def test_device_environment_sanitation(device_exec_env: Dict[str, Any]) -> None:
    """Verify that dangerous environment variables and secrets are stripped."""
    config: TacpConfig = device_exec_env["config"]
    ws_root: Path = device_exec_env["ws_root"]
    resolver = ExecutionResolver(config.limits)

    dirty_env = {
        "LD_PRELOAD": "/system/lib64/libhacked.so",
        "PYTHONPATH": "/opt/malicious",
        "AWS_SECRET_ACCESS_KEY": "supersecretkey123",
        "MY_APP_SETTING": "clean_value",
    }
    assembled = dict(resolver.assemble_environment(ws_root, str(ws_root), dirty_env))

    assert "LD_PRELOAD" not in assembled
    assert "PYTHONPATH" not in assembled
    assert "AWS_SECRET_ACCESS_KEY" not in assembled
    assert assembled.get("MY_APP_SETTING") == "clean_value"
    assert "PATH" in assembled
    assert "TMPDIR" in assembled
