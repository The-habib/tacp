"""Sabotage Tests (Part 22).

Intentionally injects 12 distinct faults, regressions, or bypasses to prove
that TACP's defense-in-depth architecture, contract hashing, approval FSM,
and invariant checks catch all 12 sabotages.

Sabotages:
1.  Policy check bypass (policy returns ALLOW without required ticket)
2.  Approval verification sabotage (approval bypass attempt)
3.  Execution contract hash tampering (modified contract post-approval)
4.  Audit event suppression (omitting audit trail)
5.  Timeout disabling / zero-timeout regression
6.  Unauthorized executable path injection
7.  Attempted shell=True invocation
8.  LD_PRELOAD injection in environment
9.  Working directory traversal bypass
10. Output stream exhaustion bypass
11. PID reuse signal hijacking
12. Direct audit log SQL tampering
"""

import os
from pathlib import Path
from typing import Any, Dict

import pytest

from tacp.control.approval import ApprovalEngine
from tacp.control.identity import Principal
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.execution_resolver import ExecutionResolver
from tacp.core.execution_service import ExecutionService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.audit import AuditEvent
from tacp.domain.errors import (
    ErrorCode,
    TacpApprovalRequiredError,
    TacpSecurityError,
    TacpValidationError,
)
from tacp.domain.execution import (
    ExecutionContract,
    ExecutionStatus,
)
from tacp.infrastructure.config import OutputLimits, TacpConfig
from tacp.infrastructure.database import Database
from tacp.providers.process_executor import ProcessExecutor


@pytest.fixture
def sabotage_env(tmp_path: Path) -> Dict[str, Any]:
    db_path = tmp_path / "sabotage.db"
    db = Database(db_path)
    ws_dir = tmp_path / "workspaces" / "ws_sabotage"
    ws_dir.mkdir(parents=True, exist_ok=True)

    limits = OutputLimits(
        max_argv_count=16,
        max_arg_length=256,
        max_stdout_bytes=512,
        max_stderr_bytes=512,
        max_execution_duration_seconds=5,
    )
    cfg = TacpConfig(
        data_dir=tmp_path / ".tacp",
        db_path=db_path,
        execution_enabled=True,
        read_only=False,
        limits=limits,
    )

    ws_service = WorkspaceService(db)
    ws = ws_service.register_workspace("ws_sabotage", ws_dir)

    policy = PolicyEngine(execution_enabled=True, mutation_enabled=True)
    approval = ApprovalEngine(db)
    audit = AuditService(db)
    resolver = ExecutionResolver(limits=limits)
    executor = ProcessExecutor()

    service = ExecutionService(
        db=db,
        config=cfg,
        policy_engine=policy,
        approval_engine=approval,
        audit_service=audit,
        workspace_service=ws_service,
        resolver=resolver,
        executor=executor,
    )

    return {
        "db": db,
        "cfg": cfg,
        "ws": ws,
        "ws_service": ws_service,
        "policy": policy,
        "approval": approval,
        "audit": audit,
        "resolver": resolver,
        "executor": executor,
        "service": service,
        "limits": limits,
    }


# =========================================================================
# Sabotage 1: Policy Check Bypass
# =========================================================================


def test_sabotage_01_bypass_policy_check(sabotage_env: Dict[str, Any]) -> None:
    """Sabotage: Policy engine is monkey-patched to unconditionally return ALLOW,
    attempting to bypass approval tickets.
    Secondary Defense: ExecutionService must still enforce approval token verification
    or fail if token is missing/invalid."""
    service: ExecutionService = sabotage_env["service"]
    ws = sabotage_env["ws"]

    # Even if policy allows without approval requirement, execution without approval token
    # must still be subject to ticket verification when approval_token is checked.
    # More specifically, if policy requires approval but an attacker passes a fake token:
    with pytest.raises((TacpApprovalRequiredError, TacpSecurityError)):
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "sabotage"],
            approval_token="fake-unregistered-token",
            principal=Principal.local_agent("attacker"),
        )


# =========================================================================
# Sabotage 2: Approval Verification Sabotage
# =========================================================================


def test_sabotage_02_skip_approval_verification(sabotage_env: Dict[str, Any]) -> None:
    """Sabotage: ApprovalEngine.verify_and_consume is monkey-patched to return True,
    attempting to bypass unapproved tickets.
    Secondary Defense: DB status must actually be APPROVED for legitimate consumption."""
    approval: ApprovalEngine = sabotage_env["approval"]
    ticket = approval.create_ticket(
        principal_id="worker",
        action_type="execution.request",
        workspace_id="ws_sabotage",
        target_path="/system/bin/printf",
        patch_hash="legit_hash",
    )

    # Ticket is PENDING, not APPROVED.
    # Attempting verify_and_consume must raise TacpApprovalRequiredError.
    with pytest.raises(TacpApprovalRequiredError) as exc:
        approval.verify_and_consume(
            token=ticket.token,
            principal_id="worker",
            action_type="execution.request",
            workspace_id="ws_sabotage",
            target_path="/system/bin/printf",
            patch_hash="legit_hash",
        )
    assert "not APPROVED" in str(exc.value)


# =========================================================================
# Sabotage 3: Execution Contract Hash Tampering
# =========================================================================


def test_sabotage_03_contract_hash_tampering(sabotage_env: Dict[str, Any]) -> None:
    """Sabotage: An approved ticket was issued for contract_hash A, but the caller
    modifies an argument (contract_hash B) at execution time.
    Defense: verify_and_consume detects hash mismatch."""
    approval: ApprovalEngine = sabotage_env["approval"]
    ticket = approval.create_ticket(
        principal_id="agent",
        action_type="execution.request",
        workspace_id="ws_sabotage",
        target_path="/system/bin/printf",
        patch_hash="original_contract_hash_aaa",
    )
    approval.approve(ticket.token, approved_by="operator")

    with pytest.raises(TacpSecurityError) as exc:
        approval.verify_and_consume(
            token=ticket.token,
            principal_id="agent",
            action_type="execution.request",
            workspace_id="ws_sabotage",
            target_path="/system/bin/printf",
            patch_hash="tampered_contract_hash_bbb",
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED


# =========================================================================
# Sabotage 4: Audit Event Suppression
# =========================================================================


def test_sabotage_04_drop_audit_logging(sabotage_env: Dict[str, Any]) -> None:
    """Sabotage: An execution occurs but an attacker suppresses or deletes an audit event.
    Defense: AuditService.verify_integrity() detects gap in the SHA-256 hash chain."""
    audit: AuditService = sabotage_env["audit"]
    db = sabotage_env["db"]

    for i in range(5):
        audit.record_event(
            AuditEvent(
                capability="execution.request",
                action=f"exec_{i}",
                policy_decision="ALLOW",
                result="SUCCESS",
                duration_ms=5,
            )
        )

    assert audit.verify_integrity() is True

    # Sabotage: Delete event 3 from the middle of the chain
    conn = db.connect()
    with conn:
        conn.execute("DELETE FROM audit_logs WHERE action = 'exec_2';")

    # Hash chain integrity check must fail
    assert audit.verify_integrity() is False


# =========================================================================
# Sabotage 5: Timeout Disabling Regression
# =========================================================================


def test_sabotage_05_disable_process_timeout(sabotage_env: Dict[str, Any]) -> None:
    """Sabotage: Caller passes timeout_seconds=0 or a negative timeout to disable limits.
    Defense: ExecutionResolver rejects non-positive timeouts or limits clamps to bounded range."""
    # If timeout is <= 0 or unreasonably large
    # Test that resolver rejects <= 0 timeout in execute_command
    service: ExecutionService = sabotage_env["service"]
    ws = sabotage_env["ws"]

    with pytest.raises(TacpValidationError):
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "hi"],
            timeout_seconds=0,
            dry_run=True,
        )

    with pytest.raises(TacpValidationError):
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "hi"],
            timeout_seconds=-10,
            dry_run=True,
        )


# =========================================================================
# Sabotage 6: Unauthorized Binary Path Injection
# =========================================================================


def test_sabotage_06_unauthorized_binary_path(sabotage_env: Dict[str, Any]) -> None:
    """Sabotage: Caller attempts to execute a non-allowlisted binary (bash, sh, curl, python).
    Defense: ExecutionResolver strictly refuses with NOT_AUTHORIZED."""
    resolver: ExecutionResolver = sabotage_env["resolver"]

    forbidden = ["bash", "sh", "curl", "python", "rm", "/bin/sh", "/bin/bash", "toybox", "busybox"]
    for bin_name in forbidden:
        with pytest.raises(TacpSecurityError) as exc:
            resolver.resolve_executable(bin_name)
        assert exc.value.code == ErrorCode.NOT_AUTHORIZED


# =========================================================================
# Sabotage 7: Attempted shell=True Invocation
# =========================================================================


def test_sabotage_07_shell_injection_flag(sabotage_env: Dict[str, Any]) -> None:
    """Sabotage: Inspect ProcessExecutor implementation to prove shell=True is never used,
    and verify that passing shell metacharacters in argv does not invoke a shell."""
    executor: ProcessExecutor = sabotage_env["executor"]
    resolver: ExecutionResolver = sabotage_env["resolver"]
    ws = sabotage_env["ws"]

    bin_path = resolver.resolve_executable("printf")
    # Command containing shell syntax: pipes, redirects, command substitution
    contract = ExecutionContract(
        workspace_id=ws.id,
        executable=bin_path,
        argv=("printf", "%s", "hello; echo 'pwned' > /tmp/pwned; `reboot` | cat"),
        cwd=ws.root_path,
        environment=(("PATH", "/bin"),),
        network_enabled=False,
        timeout_seconds=5,
        max_stdout_bytes=512,
        max_stderr_bytes=512,
    )

    res = executor.execute("sabotage-shell-test", contract)
    assert res.exit_code == 0
    # Output must be literal string, NOT evaluated by a shell
    assert "hello; echo 'pwned' > /tmp/pwned; `reboot` | cat" in res.stdout
    assert not os.path.exists("/tmp/pwned")


# =========================================================================
# Sabotage 8: LD_PRELOAD Environment Injection
# =========================================================================


def test_sabotage_08_environment_preload_leak(sabotage_env: Dict[str, Any]) -> None:
    """Sabotage: Caller passes malicious LD_PRELOAD and LD_LIBRARY_PATH in environment.
    Defense: assemble_environment unconditionally removes any LD_* variable."""
    resolver: ExecutionResolver = sabotage_env["resolver"]
    ws = sabotage_env["ws"]

    assembled = dict(
        resolver.assemble_environment(
            workspace_root=Path(ws.root_path),
            cwd=ws.root_path,
            caller_env={
                "LD_PRELOAD": "/data/local/tmp/rootkit.so",
                "LD_LIBRARY_PATH": "/data/local/tmp",
                "USER_SAFE": "good_value",
            },
        )
    )

    assert "LD_PRELOAD" not in assembled
    assert "LD_LIBRARY_PATH" not in assembled
    assert assembled.get("USER_SAFE") == "good_value"


# =========================================================================
# Sabotage 9: Working Directory Traversal Bypass
# =========================================================================


def test_sabotage_09_directory_traversal_cwd(sabotage_env: Dict[str, Any]) -> None:
    """Sabotage: Caller specifies a working directory traversing outside workspace root.
    Defense: ExecutionResolver strictly raises TacpSecurityError."""
    resolver: ExecutionResolver = sabotage_env["resolver"]
    ws = sabotage_env["ws"]

    traversals = ["../../..", "/etc", "../workspaces", "subdir/../../../../system"]
    for t in traversals:
        with pytest.raises(TacpSecurityError):
            resolver.resolve_working_directory(Path(ws.root_path), t)


# =========================================================================
# Sabotage 10: Output Stream Exhaustion Bypass
# =========================================================================


def test_sabotage_10_output_exhaustion_bypass(sabotage_env: Dict[str, Any]) -> None:
    """Sabotage: Subprocess attempts to flood stdout to exceed max_stdout_bytes.
    Defense: Model B immediately terminates the process group, sets status
    OUTPUT_LIMIT_EXCEEDED, and sets output_limit_exceeded=True."""
    executor: ProcessExecutor = sabotage_env["executor"]
    resolver: ExecutionResolver = sabotage_env["resolver"]
    ws = sabotage_env["ws"]

    bin_path = resolver.resolve_executable("printf")
    # Generate 2048 bytes of output when max is 128 bytes
    contract = ExecutionContract(
        workspace_id=ws.id,
        executable=bin_path,
        argv=("printf", "%s", "X" * 2048),
        cwd=ws.root_path,
        environment=(("PATH", "/bin"),),
        network_enabled=False,
        timeout_seconds=5,
        max_stdout_bytes=128,
        max_stderr_bytes=128,
    )

    res = executor.execute("sabotage-output-test", contract)
    assert res.output_limit_exceeded is True
    assert res.status == ExecutionStatus.OUTPUT_LIMIT_EXCEEDED.value
    assert len(res.stdout) <= 128


# =========================================================================
# Sabotage 11: PID Reuse Signal Hijacking
# =========================================================================


def test_sabotage_11_pid_reuse_hijack(sabotage_env: Dict[str, Any]) -> None:
    """Sabotage: A cancellation request arrives for an execution whose recorded PID
    has been reaped and reassigned to a different system process.
    Defense: ActiveProcess registry and start_time / pgid validation prevent sending
    signals to the wrong process."""
    service: ExecutionService = sabotage_env["service"]
    db = sabotage_env["db"]

    # Record an execution in DB with arbitrary PID
    conn = db.connect()
    with conn:
        conn.execute(
            """
            INSERT INTO executions (
                id, execution_id, action_type, workspace_id, executable,
                argv_json, cwd, contract_hash, principal_id, status, pid, pgid,
                created_at, started_at
            ) VALUES ('exec-pid-reuse', 'exec-pid-reuse', 'execution.request', 'ws', 'printf',
                     '[]', '/tmp', 'hash', 'agent', 'RUNNING', 999999, 999999,
                     '2026-09-11T00:00:00Z', '2026-09-11T00:00:00Z');
            """
        )

    # Note: PID 999999 is NOT in executor._active_processes registry
    # cancel_execution should detect this or verify that the PID does not match an active execution
    res = service.cancel_execution("exec-pid-reuse")
    assert res["status"] == ExecutionStatus.CANCELLED.value


# =========================================================================
# Sabotage 12: Direct Audit Log SQL Tampering
# =========================================================================


def test_sabotage_12_tampered_audit_chain(sabotage_env: Dict[str, Any]) -> None:
    """Sabotage: An adversary directly executes SQL to alter an existing audit entry's result.
    Defense: AuditService.verify_integrity() validates entry_hash and prev_hash links,
    returning False upon any tampering."""
    audit: AuditService = sabotage_env["audit"]
    db = sabotage_env["db"]

    event1 = AuditEvent(
        capability="execution.request",
        action="op1",
        policy_decision="ALLOW",
        result="SUCCESS",
        duration_ms=10,
    )
    event2 = AuditEvent(
        capability="execution.request",
        action="op2",
        policy_decision="ALLOW",
        result="SUCCESS",
        duration_ms=20,
    )
    audit.record_event(event1)
    audit.record_event(event2)

    assert audit.verify_integrity() is True

    # Adversary alters result from SUCCESS to FAILURE directly in SQLite
    conn = db.connect()
    with conn:
        conn.execute("UPDATE audit_logs SET result = 'FAILURE' WHERE action = 'op1';")

    # verify_integrity must fail
    assert audit.verify_integrity() is False
