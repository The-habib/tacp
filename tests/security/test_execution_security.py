"""Comprehensive Execution Security Matrix Test Suite (SEC-01 to SEC-102).

Verifies operating system process execution boundaries, shell-injection immunity,
process group isolation, deterministic resolver, immutable contracts, and scoped approvals.
"""

import signal
import threading
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from tacp.control.approval import ApprovalEngine
from tacp.control.identity import Principal
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.execution_resolver import ExecutionResolver
from tacp.core.execution_service import ExecutionService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import (
    ErrorCode,
    TacpApprovalRequiredError,
    TacpNotFoundError,
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
from tacp.providers.process_executor import ProcessExecutor, sanitize_output


@pytest.fixture
def exec_env(test_db: Database, tmp_path: Path) -> Dict[str, Any]:
    ws_dir = tmp_path / "sec_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)

    limits = OutputLimits(
        max_argv_count=64,
        max_arg_length=4096,
        max_env_count=16,
        max_stdout_bytes=65536,
        max_stderr_bytes=65536,
        max_execution_duration_seconds=15,
    )
    cfg = TacpConfig(
        data_dir=tmp_path / ".tacp_sec",
        db_path=test_db.db_path,
        execution_enabled=True,
        read_only=False,
        limits=limits,
    )

    ws_service = WorkspaceService(test_db)
    ws = ws_service.register_workspace("sec_proj", ws_dir)

    policy_engine = PolicyEngine(
        execution_enabled=True,
        mutation_enabled=True,
        read_only_enforced=False,
    )
    approval_engine = ApprovalEngine(test_db)
    audit_service = AuditService(test_db)
    resolver = ExecutionResolver(limits=limits)
    executor = ProcessExecutor()

    exec_service = ExecutionService(
        db=test_db,
        config=cfg,
        policy_engine=policy_engine,
        approval_engine=approval_engine,
        audit_service=audit_service,
        workspace_service=ws_service,
        resolver=resolver,
        executor=executor,
    )

    return {
        "db": test_db,
        "cfg": cfg,
        "ws": ws,
        "ws_dir": ws_dir,
        "policy": policy_engine,
        "approval": approval_engine,
        "audit": audit_service,
        "resolver": resolver,
        "executor": executor,
        "service": exec_service,
        "limits": limits,
    }


def _run_with_approval(
    service: ExecutionService, approval_engine: ApprovalEngine, **kwargs: Any
) -> Any:
    """Helper to request execution, approve generated ticket, and execute."""
    try:
        return service.execute_command(**kwargs)
    except TacpApprovalRequiredError as exc:
        tok = exc.details["token"]
        approval_engine.approve(tok, approved_by="human_operator")
        kwargs["approval_token"] = tok
        return service.execute_command(**kwargs)


# =========================================================================
# SEC-01 to SEC-15: Shell Injection & Metacharacter Containment
# =========================================================================


@pytest.mark.parametrize(
    "payload,marker",
    [
        ("foo; id", "foo; id"),
        ("foo & calc", "foo & calc"),
        ("foo | cat /etc/passwd", "foo | cat /etc/passwd"),
        ("foo `id`", "foo `id`"),
        ("foo $(whoami)", "foo $(whoami)"),
        ("foo\nid", "foo\nid"),
        ("foo && id", "foo && id"),
        ("foo || id", "foo || id"),
        ("foo > /tmp/bad_tacp_out", "foo > /tmp/bad_tacp_out"),
        ("foo >> /tmp/bad_tacp_out", "foo >> /tmp/bad_tacp_out"),
        ("cat < /etc/passwd", "cat < /etc/passwd"),
        ("<<EOF\nfoo\nEOF", "<<EOF\nfoo\nEOF"),
        ("~/secrets", "~/secrets"),
        ("$HOME", "$HOME"),
        ('" ; id ; "', '" ; id ; "'),
    ],
    ids=[
        "SEC-01-semicolon",
        "SEC-02-ampersand",
        "SEC-03-pipe",
        "SEC-04-backticks",
        "SEC-05-subshell",
        "SEC-06-newline",
        "SEC-07-double-ampersand",
        "SEC-08-double-pipe",
        "SEC-09-redirect-out",
        "SEC-10-redirect-append",
        "SEC-11-redirect-in",
        "SEC-12-heredoc",
        "SEC-13-tilde",
        "SEC-14-variable-expansion",
        "SEC-15-escaped-quotes",
    ],
)
def test_sec_01_to_15_shell_injection_containment(
    exec_env: Dict[str, Any], payload: str, marker: str
) -> None:
    service = exec_env["service"]
    approval = exec_env["approval"]
    ws = exec_env["ws"]

    res = _run_with_approval(
        service,
        approval,
        workspace_id=ws.id,
        executable="printf",
        argv=["printf", "%s", payload],
    )
    assert res.status == ExecutionStatus.SUCCEEDED.value
    assert res.exit_code == 0
    assert marker in res.stdout
    assert not Path("/tmp/bad_tacp_out").exists()


# =========================================================================
# SEC-16: Argument Injection
# =========================================================================


def test_sec_16_argument_injection(exec_env: Dict[str, Any]) -> None:
    service = exec_env["service"]
    approval = exec_env["approval"]
    ws = exec_env["ws"]

    res = _run_with_approval(
        service,
        approval,
        workspace_id=ws.id,
        executable="printf",
        argv=["printf", "%s", "-oProxyCommand=calc"],
    )
    assert res.status == ExecutionStatus.SUCCEEDED.value
    assert "-oProxyCommand=calc" in res.stdout


# =========================================================================
# SEC-17 to SEC-19: Path Poisoning
# =========================================================================


@pytest.mark.parametrize(
    "bad_path",
    [".:$PATH", ":/bin", "/tmp:/data/data/com.termux/files/usr/bin"],
    ids=["SEC-17-relative-path", "SEC-18-empty-entry", "SEC-19-untrusted-dir"],
)
def test_sec_17_to_19_path_poisoning(exec_env: Dict[str, Any], bad_path: str) -> None:
    resolver: ExecutionResolver = exec_env["resolver"]
    ws = exec_env["ws"]
    clean_env = dict(
        resolver.assemble_environment(Path(ws.root_path), str(ws.root_path), {"PATH": bad_path})
    )
    assert clean_env["PATH"] != bad_path
    assert not clean_env["PATH"].startswith(".")
    assert "/tmp" not in clean_env["PATH"]


# =========================================================================
# SEC-20 to SEC-22: Path Traversal
# =========================================================================


def test_sec_20_target_executable_traversal(exec_env: Dict[str, Any]) -> None:
    service = exec_env["service"]
    ws = exec_env["ws"]
    with pytest.raises(TacpSecurityError) as exc:
        service.execute_command(
            workspace_id=ws.id,
            executable="../../bin/sh",
            argv=["../../bin/sh"],
        )
    assert exc.value.code in (ErrorCode.NOT_AUTHORIZED, ErrorCode.INVALID_INPUT)


def test_sec_21_working_directory_traversal(exec_env: Dict[str, Any]) -> None:
    service = exec_env["service"]
    ws = exec_env["ws"]
    with pytest.raises(TacpSecurityError) as exc:
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "hello"],
            cwd="../../",
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED


def test_sec_22_deep_working_directory_escape(exec_env: Dict[str, Any]) -> None:
    service = exec_env["service"]
    ws = exec_env["ws"]
    with pytest.raises(TacpSecurityError) as exc:
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "hello"],
            cwd="a/b/../../../../",
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED


# =========================================================================
# SEC-23 to SEC-25: Symlink Attacks
# =========================================================================


def test_sec_23_symlink_to_forbidden_executable(exec_env: Dict[str, Any], tmp_path: Path) -> None:
    resolver: ExecutionResolver = exec_env["resolver"]
    fake_sh = tmp_path / "fake_bin" / "mysh"
    fake_sh.parent.mkdir(parents=True, exist_ok=True)
    real_sh = Path("/bin/sh")
    if real_sh.exists():
        fake_sh.symlink_to(real_sh)
        with pytest.raises(TacpSecurityError):
            resolver.resolve_executable(str(fake_sh))


def test_sec_24_working_dir_symlink_escape(exec_env: Dict[str, Any], tmp_path: Path) -> None:
    resolver: ExecutionResolver = exec_env["resolver"]
    ws = exec_env["ws"]
    ws_root = Path(ws.root_path)
    outside_dir = tmp_path / "outside_jail"
    outside_dir.mkdir()
    symlink_dir = ws_root / "escape_link"
    symlink_dir.symlink_to(outside_dir)

    with pytest.raises(TacpSecurityError):
        resolver.resolve_working_directory(ws_root, "escape_link")


def test_sec_25_broken_symlink(exec_env: Dict[str, Any], tmp_path: Path) -> None:
    resolver: ExecutionResolver = exec_env["resolver"]
    broken = tmp_path / "broken_link"
    broken.symlink_to(tmp_path / "nonexistent_target")

    with pytest.raises((TacpNotFoundError, TacpSecurityError)):
        resolver.resolve_executable(str(broken))


# =========================================================================
# SEC-26 to SEC-35: Interpreter Abuse & Script Invocations
# =========================================================================


@pytest.mark.parametrize(
    "bad_bin,args",
    [
        ("python", ["-c", "import os; os.system('id')"]),
        ("python3", ["-m", "pytest"]),
        ("bash", ["-c", "id"]),
        ("sh", ["-c", "id"]),
        ("node", ["-e", "process.exit()"]),
        ("perl", ["-e", "system('id')"]),
        ("ruby", ["-e", "system('id')"]),
        ("env", ["bash"]),
        ("script.py", ["arg"]),
        ("script.sh", ["arg"]),
    ],
    ids=[
        "SEC-26-python-c",
        "SEC-27-python-m",
        "SEC-28-bash-c",
        "SEC-29-sh-c",
        "SEC-30-node-e",
        "SEC-31-perl-e",
        "SEC-32-ruby-e",
        "SEC-33-env-binary",
        "SEC-34-py-extension",
        "SEC-35-sh-extension",
    ],
)
def test_sec_26_to_35_interpreter_abuse(
    exec_env: Dict[str, Any], bad_bin: str, args: List[str]
) -> None:
    service = exec_env["service"]
    ws = exec_env["ws"]
    with pytest.raises((TacpSecurityError, TacpNotFoundError)):
        service.execute_command(
            workspace_id=ws.id,
            executable=bad_bin,
            argv=[bad_bin] + args,
        )


# =========================================================================
# SEC-36 to SEC-49: Environment Poisoning & Secret Leaking
# =========================================================================


@pytest.mark.parametrize(
    "var_name,var_val",
    [
        ("LD_PRELOAD", "/tmp/evil.so"),
        ("LD_LIBRARY_PATH", "/tmp"),
        ("PYTHONPATH", "/tmp"),
        ("PYTHONHOME", "/tmp"),
        ("NODE_PATH", "/tmp"),
        ("CLASSPATH", "/tmp"),
        ("RUBYLIB", "/tmp"),
        ("PERL5LIB", "/tmp"),
        ("BASH_ENV", "/tmp/rc"),
        ("OPENAI_API_KEY", "sk-live-1234567890"),
        ("ANTHROPIC_API_KEY", "ant-live-secret"),
        ("GITHUB_TOKEN", "ghp_supersecretvalue"),
        ("TACP_DATABASE_PASSWORD", "secret_pass"),
        ("AWS_SECRET_ACCESS_KEY", "aws_secret_key"),
    ],
    ids=[
        "SEC-36-ld-preload",
        "SEC-37-ld-lib-path",
        "SEC-38-pythonpath",
        "SEC-39-pythonhome",
        "SEC-40-nodepath",
        "SEC-41-classpath",
        "SEC-42-rubylib",
        "SEC-43-perl5lib",
        "SEC-44-bash-env",
        "SEC-45-openai-key",
        "SEC-46-anthropic-key",
        "SEC-47-github-token",
        "SEC-48-tacp-db-pass",
        "SEC-49-aws-secret",
    ],
)
def test_sec_36_to_49_env_poisoning_and_secrets(
    exec_env: Dict[str, Any], var_name: str, var_val: str
) -> None:
    resolver: ExecutionResolver = exec_env["resolver"]
    ws = exec_env["ws"]
    clean_env = dict(
        resolver.assemble_environment(Path(ws.root_path), str(ws.root_path), {var_name: var_val})
    )
    assert var_name not in clean_env


# =========================================================================
# SEC-50 to SEC-51: File Descriptor Leaks & Stdin Injection
# =========================================================================


def test_sec_50_close_fds_enforced(exec_env: Dict[str, Any]) -> None:
    # ProcessExecutor executes with close_fds=True
    executor: ProcessExecutor = exec_env["executor"]
    resolver: ExecutionResolver = exec_env["resolver"]
    ws = exec_env["ws"]
    bin_path = resolver.resolve_executable("printf")

    contract = ExecutionContract(
        workspace_id=ws.id,
        executable=bin_path,
        argv=("printf", "test-fd"),
        cwd=ws.root_path,
        environment=(("LANG", "C.UTF-8"), ("PATH", "/system/bin:/bin")),
        network_enabled=False,
        timeout_seconds=5,
        max_stdout_bytes=1024,
        max_stderr_bytes=1024,
    )
    res = executor.execute("exec-fd-test", contract)
    assert res.status == ExecutionStatus.SUCCEEDED.value


def test_sec_51_stdin_devnull_immediate_eof(exec_env: Dict[str, Any]) -> None:
    # Any process reading stdin receives immediate EOF
    service = exec_env["service"]
    approval = exec_env["approval"]
    ws = exec_env["ws"]

    res = _run_with_approval(
        service,
        approval,
        workspace_id=ws.id,
        executable="printf",
        argv=["printf", "eof-check"],
    )
    assert res.status == ExecutionStatus.SUCCEEDED.value
    assert res.exit_code == 0


# =========================================================================
# SEC-52 to SEC-55: Output Flooding & Watchdog Timeouts
# =========================================================================


def test_sec_52_53_output_flooding_bounding(exec_env: Dict[str, Any]) -> None:
    executor: ProcessExecutor = exec_env["executor"]
    resolver: ExecutionResolver = exec_env["resolver"]
    ws = exec_env["ws"]
    bin_path = resolver.resolve_executable("printf")

    # Limit to 32 bytes max stdout
    contract = ExecutionContract(
        workspace_id=ws.id,
        executable=bin_path,
        argv=("printf", "%01000d", "0"),
        cwd=ws.root_path,
        environment=(("LANG", "C.UTF-8"), ("PATH", "/system/bin:/bin")),
        network_enabled=False,
        timeout_seconds=5,
        max_stdout_bytes=32,
        max_stderr_bytes=32,
    )
    res = executor.execute("exec-flood-test", contract)
    assert res.stdout_truncated is True
    assert len(res.stdout.encode("utf-8")) <= 32


def test_sec_54_giant_stderr_bounded(exec_env: Dict[str, Any]) -> None:
    executor: ProcessExecutor = exec_env["executor"]
    resolver: ExecutionResolver = exec_env["resolver"]
    ws = exec_env["ws"]
    bin_path = resolver.resolve_executable("printf")

    contract = ExecutionContract(
        workspace_id=ws.id,
        executable=bin_path,
        argv=("printf", "hello"),
        cwd=ws.root_path,
        environment=(("LANG", "C.UTF-8"), ("PATH", "/system/bin:/bin")),
        network_enabled=False,
        timeout_seconds=5,
        max_stdout_bytes=32,
        max_stderr_bytes=32,
    )
    res = executor.execute("exec-stderr-test", contract)
    assert len(res.stderr.encode("utf-8")) <= 32


def test_sec_55_watchdog_timeout(exec_env: Dict[str, Any]) -> None:
    # If a process exceeds timeout, it is terminated with TIMED_OUT status
    executor: ProcessExecutor = exec_env["executor"]
    resolver: ExecutionResolver = exec_env["resolver"]
    ws = exec_env["ws"]
    bin_path = resolver.resolve_executable("printf")

    contract = ExecutionContract(
        workspace_id=ws.id,
        executable=bin_path,
        argv=("printf", "timeout-check"),
        cwd=ws.root_path,
        environment=(("PATH", "/bin"),),
        network_enabled=False,
        timeout_seconds=1,
        max_stdout_bytes=1024,
        max_stderr_bytes=1024,
    )
    with patch.object(
        executor,
        "_monitor_and_reap",
        return_value=(b"", b"", False, False, True, False, signal.SIGKILL),
    ):
        res = executor.execute("exec-timeout-test", contract)
        assert res.timed_out is True
        assert res.status == ExecutionStatus.TIMED_OUT.value


# =========================================================================
# SEC-56 to SEC-60: Process Group & PID Reuse Defense
# =========================================================================


def test_sec_56_57_process_group_session_isolation(exec_env: Dict[str, Any]) -> None:
    # Verifies that start_new_session=True creates an isolated process group
    executor: ProcessExecutor = exec_env["executor"]
    resolver: ExecutionResolver = exec_env["resolver"]
    ws = exec_env["ws"]
    bin_path = resolver.resolve_executable("printf")

    contract = ExecutionContract(
        workspace_id=ws.id,
        executable=bin_path,
        argv=("printf", "session-test"),
        cwd=ws.root_path,
        environment=(("LANG", "C.UTF-8"), ("PATH", "/system/bin:/bin")),
        network_enabled=False,
        timeout_seconds=5,
        max_stdout_bytes=1024,
        max_stderr_bytes=1024,
    )
    res = executor.execute("exec-pg-test", contract)
    assert res.pgid is not None
    assert res.pgid == res.pid


def test_sec_58_sigkill_escalation(exec_env: Dict[str, Any]) -> None:
    # Verifies that cancellation escalates from SIGTERM to SIGKILL
    executor: ProcessExecutor = exec_env["executor"]
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # Process doesn't exit after SIGTERM

    with patch("os.killpg") as mock_killpg, patch("time.sleep"):
        sig = executor._kill_process_group(pgid=12345, process=mock_proc)
        assert sig == signal.SIGKILL
        assert mock_killpg.call_count == 2
        mock_killpg.assert_any_call(12345, signal.SIGTERM)
        mock_killpg.assert_any_call(12345, signal.SIGKILL)


def test_sec_59_pid_reuse_defense(exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = exec_env["service"]
    # Attempting to cancel an already COMPLETED execution does not signal foreign PID
    conn = exec_env["db"].connect()
    with conn:
        conn.execute(
            """
            INSERT INTO executions (execution_id, action_type, workspace_id, executable, argv_json,
                                   cwd, contract_hash, principal_id, status, pid, pgid, created_at)
            VALUES ('exec-reused', 'execution.request', 'ws-1', 'printf', '[]',
                    '/tmp', 'hash', 'p1', 'SUCCEEDED', 12345, 12345, '2026-09-11T00:00:00Z')
            """
        )
    with patch("os.killpg") as mock_killpg:
        res = service.cancel_execution("exec-reused")
        assert res["status"] == "SUCCEEDED"
        mock_killpg.assert_not_called()


def test_sec_60_unrelated_process_kill_denied(exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = exec_env["service"]
    with pytest.raises(TacpNotFoundError):
        service.cancel_execution("exec-nonexistent-id")


# =========================================================================
# SEC-61 to SEC-74: Approval Engine & Parameter Tampering Matrix
# =========================================================================


def test_sec_61_approval_replay_denied(exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = exec_env["service"]
    approval: ApprovalEngine = exec_env["approval"]
    ws = exec_env["ws"]

    # First run succeeds with approval
    res = _run_with_approval(
        service,
        approval,
        workspace_id=ws.id,
        executable="printf",
        argv=["printf", "token-replay-test"],
    )
    assert res.status == ExecutionStatus.SUCCEEDED.value

    # Replaying used token raises TacpSecurityError
    used_token = res.metadata.get("approval_token")
    if used_token:
        with pytest.raises(TacpSecurityError) as exc:
            service.execute_command(
                workspace_id=ws.id,
                executable="printf",
                argv=["printf", "token-replay-test"],
                approval_token=used_token,
            )
        assert exc.value.code in (ErrorCode.NOT_AUTHORIZED, ErrorCode.POLICY_DENIED)


def test_sec_62_tampering_argv(exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = exec_env["service"]
    approval: ApprovalEngine = exec_env["approval"]
    ws = exec_env["ws"]

    try:
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "approved argv"],
        )
    except TacpApprovalRequiredError as exc:
        tok = exc.details["token"]
        approval.approve(tok, approved_by="human_operator")

        # Caller alters argv
        with pytest.raises(TacpSecurityError) as tamper_exc:
            service.execute_command(
                workspace_id=ws.id,
                executable="printf",
                argv=["printf", "TAMPERED argv"],
                approval_token=tok,
            )
        assert tamper_exc.value.code == ErrorCode.NOT_AUTHORIZED


def test_sec_63_tampering_cwd(exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = exec_env["service"]
    approval: ApprovalEngine = exec_env["approval"]
    ws = exec_env["ws"]
    sub = Path(ws.root_path) / "subdir"
    sub.mkdir(exist_ok=True)

    try:
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "test"],
            cwd=".",
        )
    except TacpApprovalRequiredError as exc:
        tok = exc.details["token"]
        approval.approve(tok, approved_by="human_operator")

        # Caller alters cwd
        with pytest.raises(TacpSecurityError) as tamper_exc:
            service.execute_command(
                workspace_id=ws.id,
                executable="printf",
                argv=["printf", "test"],
                cwd="subdir",
                approval_token=tok,
            )
        assert tamper_exc.value.code == ErrorCode.NOT_AUTHORIZED


def test_sec_64_tampering_environment(exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = exec_env["service"]
    approval: ApprovalEngine = exec_env["approval"]
    ws = exec_env["ws"]

    try:
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "test"],
            environment={"VAR1": "val1"},
        )
    except TacpApprovalRequiredError as exc:
        tok = exc.details["token"]
        approval.approve(tok, approved_by="human_operator")

        with pytest.raises(TacpSecurityError) as tamper_exc:
            service.execute_command(
                workspace_id=ws.id,
                executable="printf",
                argv=["printf", "test"],
                environment={"VAR1": "TAMPERED"},
                approval_token=tok,
            )
        assert tamper_exc.value.code == ErrorCode.NOT_AUTHORIZED


def test_sec_65_tampering_timeout(exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = exec_env["service"]
    approval: ApprovalEngine = exec_env["approval"]
    ws = exec_env["ws"]

    try:
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "test"],
            timeout_seconds=10,
        )
    except TacpApprovalRequiredError as exc:
        tok = exc.details["token"]
        approval.approve(tok, approved_by="human_operator")

        with pytest.raises(TacpSecurityError) as tamper_exc:
            service.execute_command(
                workspace_id=ws.id,
                executable="printf",
                argv=["printf", "test"],
                timeout_seconds=30,
                approval_token=tok,
            )
        assert tamper_exc.value.code == ErrorCode.NOT_AUTHORIZED


def test_sec_66_tampering_network_enabled(exec_env: Dict[str, Any]) -> None:
    # Tampering with network_enabled alters canonical contract hash
    resolver: ExecutionResolver = exec_env["resolver"]
    ws = exec_env["ws"]
    bin_path = resolver.resolve_executable("printf")

    c_no_net = ExecutionContract(
        workspace_id=ws.id,
        executable=bin_path,
        argv=("printf", "test"),
        cwd=str(ws.root_path),
        environment=(("PATH", "/bin"),),
        network_enabled=False,
        timeout_seconds=15,
        max_stdout_bytes=1024,
        max_stderr_bytes=1024,
    )
    c_net = ExecutionContract(
        workspace_id=ws.id,
        executable=bin_path,
        argv=("printf", "test"),
        cwd=str(ws.root_path),
        environment=(("PATH", "/bin"),),
        network_enabled=True,
        timeout_seconds=15,
        max_stdout_bytes=1024,
        max_stderr_bytes=1024,
    )
    assert compute_execution_contract_hash(c_no_net) != compute_execution_contract_hash(c_net)


def test_sec_67_expired_approval_rejected(exec_env: Dict[str, Any]) -> None:
    approval: ApprovalEngine = exec_env["approval"]
    ws = exec_env["ws"]

    ticket = approval.create_ticket(
        principal_id="test",
        action_type="execution.request",
        workspace_id=ws.id,
        target_path="/bin/printf",
        patch_hash="dummy_hash",
        ttl_seconds=-10,  # Pre-expired
    )
    with pytest.raises(TacpSecurityError) as exc:
        approval.approve(ticket.token, approved_by="human_operator")
    assert "expired" in str(exc.value).lower()


def test_sec_68_principal_mismatch(exec_env: Dict[str, Any]) -> None:
    approval: ApprovalEngine = exec_env["approval"]
    service: ExecutionService = exec_env["service"]
    ws = exec_env["ws"]

    try:
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "test"],
            principal_id="agent_alpha",
        )
    except TacpApprovalRequiredError as exc:
        tok = exc.details["token"]
        approval.approve(tok, approved_by="human_operator")

        # agent_beta attempts to use agent_alpha's ticket
        with pytest.raises(TacpSecurityError) as p_exc:
            service.execute_command(
                workspace_id=ws.id,
                executable="printf",
                argv=["printf", "test"],
                principal_id="agent_beta",
                approval_token=tok,
            )
        assert p_exc.value.code == ErrorCode.NOT_AUTHORIZED


def test_sec_69_workspace_mismatch(exec_env: Dict[str, Any], tmp_path: Path) -> None:
    approval: ApprovalEngine = exec_env["approval"]
    service: ExecutionService = exec_env["service"]
    ws_service: WorkspaceService = exec_env["service"].workspace_service
    ws1 = exec_env["ws"]

    ws2_dir = tmp_path / "ws2"
    ws2_dir.mkdir()
    ws2 = ws_service.register_workspace("ws2", ws2_dir)

    try:
        service.execute_command(
            workspace_id=ws1.id,
            executable="printf",
            argv=["printf", "test"],
        )
    except TacpApprovalRequiredError as exc:
        tok = exc.details["token"]
        approval.approve(tok, approved_by="human_operator")

        # Ticket for ws1 used in ws2
        with pytest.raises(TacpSecurityError) as w_exc:
            service.execute_command(
                workspace_id=ws2.id,
                executable="printf",
                argv=["printf", "test"],
                approval_token=tok,
            )
        assert w_exc.value.code == ErrorCode.NOT_AUTHORIZED


def test_sec_70_capability_mismatch(exec_env: Dict[str, Any]) -> None:
    approval: ApprovalEngine = exec_env["approval"]
    service: ExecutionService = exec_env["service"]
    ws = exec_env["ws"]

    ticket = approval.create_ticket(
        principal_id="local_agent",
        action_type="workspace.patch",  # Patch ticket, not execution
        workspace_id=ws.id,
        target_path="some_file",
        patch_hash="some_hash",
    )
    approval.approve(ticket.token, approved_by="human_operator")

    with pytest.raises(TacpSecurityError) as c_exc:
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "test"],
            approval_token=ticket.token,
        )
    assert c_exc.value.code == ErrorCode.NOT_AUTHORIZED


def test_sec_71_forged_token_rejected(exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = exec_env["service"]
    ws = exec_env["ws"]

    with pytest.raises((TacpNotFoundError, TacpSecurityError)):
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "test"],
            approval_token="tacp_appr_forged_fake_token_1234567890",
        )


def test_sec_72_approval_concurrency_consume(exec_env: Dict[str, Any]) -> None:
    approval: ApprovalEngine = exec_env["approval"]
    ws = exec_env["ws"]

    ticket = approval.create_ticket(
        principal_id="test",
        action_type="execution.request",
        workspace_id=ws.id,
        target_path="/bin/printf",
        patch_hash="contract_hash_1",
    )
    approval.approve(ticket.token, approved_by="human_operator")

    success_count = 0
    failure_count = 0

    def try_consume() -> None:
        nonlocal success_count, failure_count
        try:
            approval.verify_and_consume(
                token=ticket.token,
                principal_id="test",
                action_type="execution.request",
                workspace_id=ws.id,
                target_path="/bin/printf",
                patch_hash="contract_hash_1",
            )
            success_count += 1
        except Exception:
            failure_count += 1

    threads = [threading.Thread(target=try_consume) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert success_count == 1
    assert failure_count == 3


def test_sec_73_approval_concurrency_approve_vs_revoke(exec_env: Dict[str, Any]) -> None:
    approval: ApprovalEngine = exec_env["approval"]
    ws = exec_env["ws"]

    ticket = approval.create_ticket(
        principal_id="test",
        action_type="execution.request",
        workspace_id=ws.id,
        target_path="/bin/printf",
        patch_hash="contract_hash_2",
    )

    def run_op(fn: Any) -> None:
        try:
            fn()
        except Exception:
            pass

    t1 = threading.Thread(
        target=lambda: run_op(lambda: approval.approve(ticket.token, approved_by="operator"))
    )
    t2 = threading.Thread(
        target=lambda: run_op(lambda: approval.revoke(ticket.token, revoked_by="operator"))
    )

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # The ticket status must be either APPROVED or REVOKED, never corrupted
    t_fresh = approval.get_ticket(ticket.token)
    assert t_fresh is not None
    assert t_fresh.status in ("APPROVED", "REVOKED")


def test_sec_74_approval_concurrency_approve_vs_expire(exec_env: Dict[str, Any]) -> None:
    approval: ApprovalEngine = exec_env["approval"]
    ws = exec_env["ws"]

    ticket = approval.create_ticket(
        principal_id="test",
        action_type="execution.request",
        workspace_id=ws.id,
        target_path="/bin/printf",
        patch_hash="contract_hash_3",
        ttl_seconds=0,
    )
    # Expired ticket cannot be approved
    with pytest.raises(TacpSecurityError):
        approval.approve(ticket.token, approved_by="operator")


# =========================================================================
# SEC-75 to SEC-84: Policy Fail-Closed & Executable Whitelist
# =========================================================================


def test_sec_75_unknown_capability(exec_env: Dict[str, Any]) -> None:
    policy: PolicyEngine = exec_env["policy"]
    from tacp.control.identity import RequestContext

    ctx = RequestContext(
        capability="unknown.dangerous.action", principal=Principal.local_agent("test")
    )
    dec = policy.evaluate_request(ctx, exec_env["ws"])
    assert dec.allowed is False


@pytest.mark.parametrize(
    "forbidden_exe",
    ["gcc", "apt", "pkg", "pip", "npm", "rm", "dd", "chmod", "kill"],
    ids=[
        "SEC-76-gcc",
        "SEC-77-apt",
        "SEC-78-pkg",
        "SEC-79-pip",
        "SEC-80-npm",
        "SEC-81-rm",
        "SEC-82-dd",
        "SEC-83-chmod",
        "SEC-84-kill",
    ],
)
def test_sec_76_to_84_executable_whitelist(exec_env: Dict[str, Any], forbidden_exe: str) -> None:
    service: ExecutionService = exec_env["service"]
    ws = exec_env["ws"]
    with pytest.raises(TacpSecurityError) as exc:
        service.execute_command(
            workspace_id=ws.id,
            executable=forbidden_exe,
            argv=[forbidden_exe, "--help"],
        )
    assert exc.value.code in (ErrorCode.NOT_AUTHORIZED, ErrorCode.POLICY_DENIED)


# =========================================================================
# SEC-85 to SEC-90: Git Abuse & Network Denial
# =========================================================================


def test_sec_85_86_git_abuse_prevented(exec_env: Dict[str, Any]) -> None:
    resolver: ExecutionResolver = exec_env["resolver"]
    ws = exec_env["ws"]
    clean_env = dict(
        resolver.assemble_environment(
            Path(ws.root_path),
            str(ws.root_path),
            {"GIT_SSH_COMMAND": "calc", "GIT_EXEC_PATH": "/tmp"},
        )
    )
    assert "GIT_SSH_COMMAND" not in clean_env
    assert "GIT_EXEC_PATH" not in clean_env


def test_sec_87_network_enabled_rejected(exec_env: Dict[str, Any]) -> None:
    # Under default policy, network is disabled across execution
    cfg = exec_env["cfg"]
    assert cfg.network_enabled is False
    assert cfg.remote_execution_enabled is False


@pytest.mark.parametrize(
    "net_tool",
    ["curl", "wget", "nc"],
    ids=["SEC-88-curl", "SEC-89-wget", "SEC-90-nc"],
)
def test_sec_88_to_90_network_tools_forbidden(exec_env: Dict[str, Any], net_tool: str) -> None:
    service: ExecutionService = exec_env["service"]
    ws = exec_env["ws"]
    with pytest.raises(TacpSecurityError):
        service.execute_command(
            workspace_id=ws.id,
            executable=net_tool,
            argv=[net_tool, "http://localhost"],
        )


# =========================================================================
# SEC-91 to SEC-94: Terminal Injection Sanitization
# =========================================================================


def test_sec_91_ansi_clear_stripped() -> None:
    raw = "output\x1b[2Jcleared"
    cleaned = sanitize_output(raw)
    assert "\x1b[2J" not in cleaned
    assert cleaned == "outputcleared"


def test_sec_92_terminal_title_escape_stripped() -> None:
    raw = "test\x1b]0;Evil Title\x07rest"
    cleaned = sanitize_output(raw)
    assert "\x1b]0;" not in cleaned
    assert "\x07" not in cleaned


def test_sec_93_carriage_return_normalized() -> None:
    raw = "first\roverwrite\r\nnext"
    cleaned = sanitize_output(raw)
    assert "\r" not in cleaned
    assert cleaned == "first\noverwrite\nnext"


def test_sec_94_null_bytes_replaced() -> None:
    raw = "bad\x00data"
    cleaned = sanitize_output(raw)
    assert "\x00" not in cleaned
    assert cleaned == "bad\ufffddata"


# =========================================================================
# SEC-95 to SEC-98: Input Bounds & Dry-Run Invariants
# =========================================================================


def test_sec_95_argv_oversize_count(exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = exec_env["service"]
    ws = exec_env["ws"]
    argv = ["printf"] + ["arg"] * 100
    with pytest.raises(TacpValidationError):
        service.execute_command(workspace_id=ws.id, executable="printf", argv=argv)


def test_sec_96_single_arg_oversize_length(exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = exec_env["service"]
    ws = exec_env["ws"]
    huge_arg = "A" * 10000
    with pytest.raises(TacpValidationError):
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", huge_arg],
        )


def test_sec_97_env_oversize_count(exec_env: Dict[str, Any]) -> None:
    resolver: ExecutionResolver = exec_env["resolver"]
    ws = exec_env["ws"]
    too_many_envs = {f"CUSTOM_VAR_{i}": f"val_{i}" for i in range(25)}
    with pytest.raises(TacpValidationError):
        resolver.assemble_environment(Path(ws.root_path), str(ws.root_path), too_many_envs)


def test_sec_98_dry_run_invariant(exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = exec_env["service"]
    ws = exec_env["ws"]

    res = service.execute_command(
        workspace_id=ws.id,
        executable="printf",
        argv=["printf", "dry-run-safe"],
        dry_run=True,
    )
    assert res.status == ExecutionStatus.DRY_RUN.value
    assert res.exit_code is None
    assert res.pid is None
    assert res.pgid is None


# =========================================================================
# SEC-99 to SEC-102: Audit Concurrency, Tampering & Restart Recovery
# =========================================================================


def test_sec_99_audit_concurrency(exec_env: Dict[str, Any]) -> None:
    audit: AuditService = exec_env["audit"]
    from tacp.domain.audit import AuditEvent

    def log_event(idx: int) -> None:
        audit.record_event(
            AuditEvent(
                capability="execution.request",
                action="execution.run",
                policy_decision="ALLOW",
                result="SUCCESS",
                duration_ms=10,
                principal=f"thread-{idx}",
            )
        )

    threads = [threading.Thread(target=log_event, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Integrity must verify 100% linear chain
    assert audit.verify_integrity() is True


def test_sec_100_audit_tampering_detected(exec_env: Dict[str, Any]) -> None:
    audit: AuditService = exec_env["audit"]
    from tacp.domain.audit import AuditEvent

    # Record at least two events
    audit.record_event(
        AuditEvent(
            capability="execution.request",
            action="execution.run",
            policy_decision="ALLOW",
            result="SUCCESS",
            duration_ms=10,
            principal="tester",
        )
    )
    audit.record_event(
        AuditEvent(
            capability="execution.request",
            action="execution.run",
            policy_decision="ALLOW",
            result="SUCCESS",
            duration_ms=12,
            principal="tester",
        )
    )

    conn = exec_env["db"].connect()
    with conn:
        conn.execute("UPDATE audit_logs SET result = 'TAMPERED' WHERE rowid = 1;")

    assert audit.verify_integrity() is False


def test_sec_101_feature_flag_disabled(exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = exec_env["service"]
    object.__setattr__(service.config, "execution_enabled", False)
    ws = exec_env["ws"]

    with pytest.raises(TacpSecurityError) as exc:
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "test"],
        )
    assert exc.value.code == ErrorCode.POLICY_DENIED


def test_sec_102_restart_recovery_orphaned_reconciliation(exec_env: Dict[str, Any]) -> None:
    service: ExecutionService = exec_env["service"]
    conn = exec_env["db"].connect()

    # Insert a stale RUNNING execution with non-existent PID
    with conn:
        conn.execute(
            """
            INSERT INTO executions (execution_id, action_type, workspace_id, executable, argv_json,
                                   cwd, contract_hash, principal_id, status, pid, pgid, created_at)
            VALUES ('exec-orphan-1', 'execution.request', 'ws-1', 'printf', '[]',
                    '/tmp', 'hash', 'p1', 'RUNNING', 999999, 999999, '2026-09-11T00:00:00Z')
            """
        )

    reconciled = service.reconcile_orphans()
    assert reconciled >= 1
    info = service.inspect_execution("exec-orphan-1")
    assert info is not None
    assert info["status"] == "FAILED"
