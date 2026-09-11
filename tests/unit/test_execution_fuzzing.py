"""Fuzzing and adversarial robustness test suite for TACP Execution Core."""

from pathlib import Path
from typing import Any, Dict

import pytest

from tacp.control.approval import ApprovalEngine
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.execution_resolver import ExecutionResolver
from tacp.core.execution_service import ExecutionService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import (
    TacpApprovalRequiredError,
    TacpSecurityError,
    TacpValidationError,
)
from tacp.domain.execution import (
    ExecutionContract,
    ExecutionStatus,
    compute_execution_contract_hash,
)
from tacp.infrastructure.config import OutputLimits, TacpConfig
from tacp.infrastructure.database import Database
from tacp.providers.process_executor import ProcessExecutor


@pytest.fixture
def fuzz_env(tmp_path: Path) -> Dict[str, Any]:
    db_path = tmp_path / "fuzz_test.db"
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

    ws_root = tmp_path / "workspaces" / "fuzz-ws"
    ws_root.mkdir(parents=True, exist_ok=True)
    ws = workspace_service.register_workspace("fuzz-ws", ws_root)

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
        "resolver": ExecutionResolver(limits),
        "executor": ProcessExecutor(),
        "limits": limits,
    }


def test_fuzz_null_bytes_in_argv(fuzz_env: Dict[str, Any]) -> None:
    service: ExecutionService = fuzz_env["service"]
    ws_id: str = fuzz_env["ws_id"]

    # Null byte in argument must be strictly rejected by security validation
    with pytest.raises(TacpSecurityError) as exc:
        service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=["printf", "hello\x00world"],
            dry_run=True,
        )
    assert "null byte" in str(exc.value).lower()


def test_fuzz_null_bytes_in_executable_name(fuzz_env: Dict[str, Any]) -> None:
    service: ExecutionService = fuzz_env["service"]
    ws_id: str = fuzz_env["ws_id"]

    with pytest.raises((TacpValidationError, TacpSecurityError)):
        service.execute_command(
            workspace_id=ws_id,
            executable="printf\x00something",
            argv=["printf\x00something", "foo"],
            dry_run=True,
        )


def test_fuzz_shell_metacharacters_literal_execution(fuzz_env: Dict[str, Any]) -> None:
    """Ensure shell metacharacters are passed as literal strings without shell interpretation."""
    service: ExecutionService = fuzz_env["service"]
    ws_id: str = fuzz_env["ws_id"]
    approval: ApprovalEngine = fuzz_env["approval"]

    metachar_payloads = [
        "; rm -rf / ;",
        "| cat /etc/passwd",
        "$(id)",
        "`whoami`",
        "foo && bar",
        "> /tmp/pwned.txt",
        "< /dev/null",
        "hello && echo hacked",
        "hello || echo hacked",
        "$PATH",
        "${HOME}",
    ]

    for payload in metachar_payloads:
        with pytest.raises(TacpApprovalRequiredError) as exc:
            service.execute_command(
                workspace_id=ws_id,
                executable="printf",
                argv=["printf", "%s", payload],
                dry_run=False,
            )
        token = exc.value.details["token"]
        approval.approve(token)

        res = service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=["printf", "%s", payload],
            approval_token=token,
            dry_run=False,
        )
        assert res.status == ExecutionStatus.SUCCEEDED.value
        # The payload must appear literally in stdout, not expanded or executed
        assert res.stdout == payload


def test_fuzz_unicode_edge_cases(fuzz_env: Dict[str, Any]) -> None:
    service: ExecutionService = fuzz_env["service"]
    ws_id: str = fuzz_env["ws_id"]
    approval: ApprovalEngine = fuzz_env["approval"]

    unicode_payloads = [
        "こんにちは世界",
        "مرحبا بالعالم",
        "🔥🚀💻🛡️",
        "\u202eRLO_test\u202c",  # Right-to-left override
        "zero\u200bwidth\u200cspace",  # Zero-width spaces
        "normal\twith\ttabs",
    ]

    for payload in unicode_payloads:
        with pytest.raises(TacpApprovalRequiredError) as exc:
            service.execute_command(
                workspace_id=ws_id,
                executable="printf",
                argv=["printf", "%s", payload],
                dry_run=False,
            )
        token = exc.value.details["token"]
        approval.approve(token)

        res = service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=["printf", "%s", payload],
            approval_token=token,
            dry_run=False,
        )
        assert res.status == ExecutionStatus.SUCCEEDED.value
        assert res.stdout == payload


def test_fuzz_oversized_argv_count(fuzz_env: Dict[str, Any]) -> None:
    service: ExecutionService = fuzz_env["service"]
    ws_id: str = fuzz_env["ws_id"]

    # Limit is 64 arguments
    huge_argv = ["printf"] + [f"arg_{i}" for i in range(100)]
    with pytest.raises(TacpValidationError) as exc:
        service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=huge_argv,
            dry_run=True,
        )
    assert "exceeds limit" in str(exc.value).lower()


def test_fuzz_oversized_single_arg_length(fuzz_env: Dict[str, Any]) -> None:
    service: ExecutionService = fuzz_env["service"]
    ws_id: str = fuzz_env["ws_id"]

    # Limit is 4096 bytes per arg
    giant_arg = "A" * 5000
    with pytest.raises(TacpValidationError) as exc:
        service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=["printf", giant_arg],
            dry_run=True,
        )
    assert "exceeds limit" in str(exc.value).lower()


def test_fuzz_oversized_env_count(fuzz_env: Dict[str, Any]) -> None:
    service: ExecutionService = fuzz_env["service"]
    ws_id: str = fuzz_env["ws_id"]

    # Limit is 16 environment variables
    giant_env = {f"KEY_{i}": f"val_{i}" for i in range(30)}
    with pytest.raises(TacpValidationError) as exc:
        service.execute_command(
            workspace_id=ws_id,
            executable="printf",
            argv=["printf", "test"],
            environment=giant_env,
            dry_run=True,
        )
    assert "env" in str(exc.value).lower()


def test_fuzz_invalid_env_keys(fuzz_env: Dict[str, Any]) -> None:
    service: ExecutionService = fuzz_env["service"]
    ws_id: str = fuzz_env["ws_id"]

    bad_keys = [
        "BAD-KEY",
        "BAD KEY",
        "123_STARTS_NUM",
        "KEY=VALUE",
        "KEY\x00NULL",
        "",
    ]
    for key in bad_keys:
        with pytest.raises(TacpValidationError):
            service.execute_command(
                workspace_id=ws_id,
                executable="printf",
                argv=["printf", "test"],
                environment={key: "value"},
                dry_run=True,
            )


def test_fuzz_extreme_timeouts(fuzz_env: Dict[str, Any]) -> None:
    service: ExecutionService = fuzz_env["service"]
    ws_id: str = fuzz_env["ws_id"]

    extreme_values: list[Any] = [-10, 0, -1, "invalid", 0.5, True, False]
    for t in extreme_values:
        with pytest.raises(TacpValidationError):
            service.execute_command(
                workspace_id=ws_id,
                executable="printf",
                argv=["printf", "test"],
                timeout_seconds=t,
                dry_run=True,
            )


def test_fuzz_contract_hash_determinism() -> None:
    """Verify compute_execution_contract_hash is deterministic across unordered env dicts."""
    c1 = ExecutionContract(
        workspace_id="ws_1",
        executable="/bin/printf",
        argv=("printf", "arg1", "arg2"),
        cwd="/tmp/ws",
        environment=(("B", "2"), ("A", "1")),
        network_enabled=False,
        timeout_seconds=10,
        max_stdout_bytes=1024,
        max_stderr_bytes=1024,
    )
    c2 = ExecutionContract(
        workspace_id="ws_1",
        executable="/bin/printf",
        argv=("printf", "arg1", "arg2"),
        cwd="/tmp/ws",
        environment=(("A", "1"), ("B", "2")),
        network_enabled=False,
        timeout_seconds=10,
        max_stdout_bytes=1024,
        max_stderr_bytes=1024,
    )
    h1 = compute_execution_contract_hash(c1)
    h2 = compute_execution_contract_hash(c2)
    assert h1 == h2
    assert len(h1) == 64
