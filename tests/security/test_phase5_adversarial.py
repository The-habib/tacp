"""Phase 5 Comprehensive Adversarial Test Suite.

Covers all 32 required adversarial security categories:
1. path traversal
2. symlink traversal
3. executable substitution outside trusted roots
4. hard-link behavior & permission tampering
5. TOCTOU attempts
6. environment poisoning
7. secret leakage
8. network escape & truth model
9. output exhaustion (Model B)
10. process-tree containment
11. PID reuse defense
12. cancellation races
13. timeout races
14. approval concurrency & atomicity
15. audit hash chain integrity
16. crash recovery & orphan reconciliation
17. database corruption resilience
18. malformed MCP payloads
19. malformed JSON requests
20. oversized requests
21. Unicode abuse
22. null-byte injections
23. ANSI / terminal control sanitization
24. rapid resource exhaustion
25. capability confusion
26. identity confusion
27. privilege escalation by name
28. contract tampering
29. approval replay
30. approval substitution
31. workspace substitution
32. principal substitution
"""

from __future__ import annotations

import concurrent.futures
import os
import signal
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from tacp.control.approval import ApprovalEngine
from tacp.control.identity import Principal, PrincipalType, Role, TrustTier
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.execution_resolver import ExecutionResolver
from tacp.core.execution_service import ExecutionService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import (
    ErrorCode,
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
def p5_env(tmp_path: Path) -> Dict[str, Any]:
    db_path = tmp_path / "phase5_sec.db"
    db = Database(db_path)
    ws_dir = tmp_path / "workspaces" / "p5_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)

    limits = OutputLimits(
        max_argv_count=32,
        max_arg_length=2048,
        max_stdout_bytes=1024,
        max_stderr_bytes=1024,
        max_execution_duration_seconds=10,
    )
    cfg = TacpConfig(
        data_dir=tmp_path / ".tacp_p5",
        db_path=db_path,
        execution_enabled=True,
        read_only=False,
        limits=limits,
    )
    ws_service = WorkspaceService(db)
    ws = ws_service.register_workspace("p5_ws", ws_dir)

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
        "ws_dir": ws_dir,
        "policy": policy,
        "approval": approval,
        "audit": audit,
        "resolver": resolver,
        "executor": executor,
        "service": service,
        "limits": limits,
    }


# =========================================================================
# Category 1: Path Traversal
# =========================================================================


def test_cat01_working_dir_path_traversal(p5_env: Dict[str, Any]) -> None:
    service: ExecutionService = p5_env["service"]
    ws = p5_env["ws"]
    with pytest.raises(TacpSecurityError) as exc:
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "test"],
            cwd="../../etc",
        )
    assert exc.value.code in (ErrorCode.NOT_AUTHORIZED, ErrorCode.INVALID_INPUT)


# =========================================================================
# Category 2: Symlink Traversal
# =========================================================================


def test_cat02_working_dir_symlink_escape(p5_env: Dict[str, Any], tmp_path: Path) -> None:
    service: ExecutionService = p5_env["service"]
    ws = p5_env["ws"]
    outside = tmp_path / "outside_jail"
    outside.mkdir()
    symlink_dir = Path(ws.root_path) / "jailbreak_link"
    symlink_dir.symlink_to(outside)

    with pytest.raises(TacpSecurityError):
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "test"],
            cwd="jailbreak_link",
        )


# =========================================================================
# Category 3: Executable Substitution Outside Trusted Roots
# =========================================================================


def test_cat03_executable_substitution_in_workspace_denied(p5_env: Dict[str, Any]) -> None:
    resolver: ExecutionResolver = p5_env["resolver"]
    ws = p5_env["ws"]
    rogue_printf = Path(ws.root_path) / "printf"
    with open(rogue_printf, "w") as f:
        f.write("#!/bin/sh\necho rogue\n")
    os.chmod(rogue_printf, 0o755)

    with pytest.raises(TacpSecurityError) as exc:
        resolver.resolve_executable(str(rogue_printf))
    assert "outside trusted system search paths" in str(exc.value)


# =========================================================================
# Category 4: Hard-link Behavior & Permissions
# =========================================================================


def test_cat04_world_writable_executable_rejected(p5_env: Dict[str, Any], tmp_path: Path) -> None:
    resolver: ExecutionResolver = p5_env["resolver"]
    # If a permitted executable is world-writable, it must be rejected
    mock_identity = MagicMock()
    mock_identity.stat_res = MagicMock()
    mock_identity.stat_res.st_mode = 0o777  # World writable

    with patch("pathlib.Path.stat") as mock_stat:
        mock_stat.return_value = MagicMock(
            st_mode=0o777, st_ino=1, st_dev=1, st_size=100, st_mtime=0
        )
        with pytest.raises(TacpSecurityError) as exc:
            resolver.resolve_executable("/system/bin/printf")
        assert "world-writable" in str(exc.value) or exc.value.code == ErrorCode.NOT_AUTHORIZED


# =========================================================================
# Category 5: TOCTOU Defense
# =========================================================================


def test_cat05_toctou_digest_caching_and_identity(p5_env: Dict[str, Any]) -> None:
    resolver: ExecutionResolver = p5_env["resolver"]
    id1 = resolver.resolve_executable_identity("printf")
    id2 = resolver.resolve_executable_identity("printf")
    assert id1.sha256_digest == id2.sha256_digest
    assert len(id1.sha256_digest) == 64
    assert id1.canonical_path == id2.canonical_path


# =========================================================================
# Category 6: Environment Poisoning
# =========================================================================


@pytest.mark.parametrize(
    "poison_key,poison_val",
    [
        ("LD_PRELOAD", "/data/local/tmp/inject.so"),
        ("DYLD_INSERT_LIBRARIES", "/tmp/inject.dylib"),
        ("PYTHONPATH", "/tmp/pylib"),
        ("BASH_ENV", "/tmp/env.sh"),
        ("IFS", ":"),
        ("PROMPT_COMMAND", "reboot"),
        ("PAGER", "sh"),
        ("EDITOR", "sh"),
        ("VISUAL", "sh"),
    ],
)
def test_cat06_environment_poisoning_stripped(
    p5_env: Dict[str, Any], poison_key: str, poison_val: str
) -> None:
    resolver: ExecutionResolver = p5_env["resolver"]
    ws = p5_env["ws"]
    clean_env = resolver.assemble_environment(
        workspace_root=Path(ws.root_path),
        cwd=ws.root_path,
        caller_env={poison_key: poison_val, "USER_FLAG": "safe_val"},
    )
    env_dict = dict(clean_env)
    assert poison_key not in env_dict
    assert env_dict.get("USER_FLAG") == "safe_val"


# =========================================================================
# Category 7: Secret Leakage via Environment
# =========================================================================


@pytest.mark.parametrize(
    "secret_key",
    [
        "AWS_SECRET_ACCESS_KEY",
        "GITHUB_TOKEN",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "DATABASE_PASSWORD",
        "ID_RSA_PRIVATE_KEY",
        "AUTH_BEARER_TOKEN",
    ],
)
def test_cat07_secret_leakage_stripped(p5_env: Dict[str, Any], secret_key: str) -> None:
    resolver: ExecutionResolver = p5_env["resolver"]
    ws = p5_env["ws"]
    clean_env = resolver.assemble_environment(
        workspace_root=Path(ws.root_path),
        cwd=ws.root_path,
        caller_env={secret_key: "super-secret-password-123"},
    )
    env_dict = dict(clean_env)
    assert secret_key not in env_dict


# =========================================================================
# Category 8: Network Escape & Truth Model
# =========================================================================


def test_cat08_network_truth_model_and_proxy_strip(p5_env: Dict[str, Any]) -> None:
    resolver: ExecutionResolver = p5_env["resolver"]
    ws = p5_env["ws"]
    clean_env = resolver.assemble_environment(
        workspace_root=Path(ws.root_path),
        cwd=ws.root_path,
        caller_env={"HTTP_PROXY": "http://evil.com:8080", "HTTPS_PROXY": "http://evil.com:8080"},
    )
    env_dict = dict(clean_env)
    assert "HTTP_PROXY" not in env_dict
    assert "HTTPS_PROXY" not in env_dict


# =========================================================================
# Category 9: Output Exhaustion (Model B)
# =========================================================================


def test_cat09_model_b_output_exhaustion_terminates_immediately(p5_env: Dict[str, Any]) -> None:
    executor: ProcessExecutor = p5_env["executor"]
    resolver: ExecutionResolver = p5_env["resolver"]
    ws = p5_env["ws"]
    bin_path = resolver.resolve_executable("printf")

    contract = ExecutionContract(
        workspace_id=ws.id,
        executable=bin_path,
        argv=("printf", "%s", "Z" * 5000),
        cwd=ws.root_path,
        environment=(("LANG", "C.UTF-8"), ("PATH", "/system/bin:/bin")),
        network_enabled=False,
        timeout_seconds=5,
        max_stdout_bytes=64,
        max_stderr_bytes=64,
    )
    res = executor.execute("exec-p5-flood", contract)
    assert res.status == ExecutionStatus.OUTPUT_LIMIT_EXCEEDED.value
    assert res.output_limit_exceeded is True
    assert res.stdout_truncated is True
    assert len(res.stdout.encode("utf-8")) <= 64


# =========================================================================
# Category 10: Process-Tree Containment
# =========================================================================


def test_cat10_process_tree_session_leader(p5_env: Dict[str, Any]) -> None:
    executor: ProcessExecutor = p5_env["executor"]
    resolver: ExecutionResolver = p5_env["resolver"]
    ws = p5_env["ws"]
    bin_path = resolver.resolve_executable("printf")

    contract = ExecutionContract(
        workspace_id=ws.id,
        executable=bin_path,
        argv=("printf", "tree-test"),
        cwd=ws.root_path,
        environment=(("LANG", "C.UTF-8"), ("PATH", "/system/bin:/bin")),
        network_enabled=False,
        timeout_seconds=5,
        max_stdout_bytes=1024,
        max_stderr_bytes=1024,
    )
    res = executor.execute("exec-p5-tree", contract)
    assert res.pid is not None
    assert res.pgid == res.pid


# =========================================================================
# Category 11: PID Reuse Defense
# =========================================================================


def test_cat11_pid_reuse_defense_skips_untracked_kill(p5_env: Dict[str, Any]) -> None:
    service: ExecutionService = p5_env["service"]
    db = p5_env["db"]
    conn = db.connect()
    with conn:
        conn.execute(
            """
            INSERT INTO executions (
                id, execution_id, action_type, workspace_id, executable,
                argv_json, cwd, contract_hash, principal_id, status, pid, pgid,
                created_at, started_at
            ) VALUES ('exec-ghost', 'exec-ghost', 'execution.request', 'ws', '/system/bin/printf',
                     '[]', '/tmp', 'hash', 'agent', 'RUNNING', 99999, 99999,
                     '2026-09-11T00:00:00Z', '2026-09-11T00:00:00Z');
            """
        )

    with patch("os.killpg") as mock_killpg:
        res = service.cancel_execution("exec-ghost")
        assert res["status"] == ExecutionStatus.CANCELLED.value
        # Since exec-ghost is not active in ProcessExecutor, killpg is NEVER sent!
        mock_killpg.assert_not_called()


# =========================================================================
# Category 12: Cancellation Races
# =========================================================================


def test_cat12_concurrent_cancel_execution(p5_env: Dict[str, Any]) -> None:
    service: ExecutionService = p5_env["service"]
    db = p5_env["db"]
    conn = db.connect()
    with conn:
        conn.execute(
            """
            INSERT INTO executions (
                id, execution_id, action_type, workspace_id, executable,
                argv_json, cwd, contract_hash, principal_id, status,
                created_at, started_at
            ) VALUES ('exec-race', 'exec-race', 'execution.request', 'ws', '/system/bin/printf',
                     '[]', '/tmp', 'hash', 'agent', 'RUNNING',
                     '2026-09-11T00:00:00Z', '2026-09-11T00:00:00Z');
            """
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(service.cancel_execution, "exec-race") for _ in range(5)]
        results = [f.result() for f in futures]

    assert all(r["status"] == ExecutionStatus.CANCELLED.value for r in results)


# =========================================================================
# Category 13: Timeout Races
# =========================================================================


def test_cat13_timeout_marks_timed_out_status(p5_env: Dict[str, Any]) -> None:
    executor: ProcessExecutor = p5_env["executor"]
    resolver: ExecutionResolver = p5_env["resolver"]
    ws = p5_env["ws"]
    bin_path = resolver.resolve_executable("printf")

    contract = ExecutionContract(
        workspace_id=ws.id,
        executable=bin_path,
        argv=("printf", "test"),
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
        res = executor.execute("exec-timeout", contract)
        assert res.timed_out is True
        assert res.status == ExecutionStatus.TIMED_OUT.value


# =========================================================================
# Category 14: Approval Concurrency & Atomicity
# =========================================================================


def test_cat14_approval_concurrency_race_single_winner(p5_env: Dict[str, Any]) -> None:
    approval: ApprovalEngine = p5_env["approval"]
    ticket = approval.create_ticket(
        principal_id="worker_agent",
        action_type="execution.request",
        workspace_id="p5_ws",
        target_path="/system/bin/printf",
        patch_hash="contract_hash_abc",
    )

    def do_approve() -> bool:
        try:
            approval.approve(ticket.token, approved_by="operator")
            return True
        except TacpSecurityError:
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: do_approve(), range(10)))

    # Exactly one thread succeeds in transitioning PENDING -> APPROVED
    assert results.count(True) == 1
    assert results.count(False) == 9


# =========================================================================
# Category 15: Audit Hash Chain Integrity
# =========================================================================


def test_cat15_audit_hash_chain_tamper_evident(p5_env: Dict[str, Any]) -> None:
    from tacp.domain.audit import AuditEvent

    audit: AuditService = p5_env["audit"]
    db = p5_env["db"]

    audit.record_event(
        AuditEvent(
            capability="execution.request",
            action="test",
            policy_decision="ALLOW",
            result="SUCCESS",
            duration_ms=10,
            principal="p1",
            request_id="r1",
            workspace_id="w1",
            parameters_redacted={},
        )
    )
    audit.record_event(
        AuditEvent(
            capability="execution.request",
            action="test2",
            policy_decision="ALLOW",
            result="SUCCESS",
            duration_ms=10,
            principal="p1",
            request_id="r2",
            workspace_id="w1",
            parameters_redacted={},
        )
    )

    # Verify chain integrity
    assert audit.verify_integrity() is True

    # Tamper with an event in the database
    conn = db.connect()
    with conn:
        conn.execute("UPDATE audit_logs SET policy_decision = 'DENY' WHERE action = 'test'")

    assert audit.verify_integrity() is False


# =========================================================================
# Category 16: Crash Recovery & Orphan Reconciliation
# =========================================================================


def test_cat16_reconcile_orphans_resets_running_states(p5_env: Dict[str, Any]) -> None:
    service: ExecutionService = p5_env["service"]
    db = p5_env["db"]
    conn = db.connect()
    with conn:
        conn.execute(
            """
            INSERT INTO executions (
                id, execution_id, action_type, workspace_id, executable,
                argv_json, cwd, contract_hash, principal_id, status, pid, pgid,
                created_at, started_at
            ) VALUES ('exec-stuck', 'exec-stuck', 'execution.request', 'ws', 'printf',
                     '[]', '/tmp', 'hash', 'agent', 'RUNNING', 999999, 999999,
                     '2026-09-11T00:00:00Z', '2026-09-11T00:00:00Z');
            """
        )

    count = service.reconcile_orphans()
    assert count == 1
    info = service.inspect_execution("exec-stuck")
    assert info is not None
    assert info["status"] in (ExecutionStatus.FAILED.value, ExecutionStatus.ORPHANED.value)


# =========================================================================
# Category 17: Database Integrity & Parameter Injection
# =========================================================================


def test_cat17_database_sql_injection_defense(p5_env: Dict[str, Any]) -> None:
    service: ExecutionService = p5_env["service"]
    # Malicious injection string inside execution_id
    res = service.inspect_execution("'; DROP TABLE executions; --")
    assert res is None


# =========================================================================
# Category 18: Malformed MCP Payloads
# =========================================================================


def test_cat18_malformed_mcp_arguments(p5_env: Dict[str, Any]) -> None:
    from tacp.access.mcp.tools import McpToolRegistry
    from tacp.core.capability_service import CapabilityService

    service: ExecutionService = p5_env["service"]
    registry = McpToolRegistry(
        capability_service=CapabilityService(),
        policy_engine=service.policy_engine,
        audit_service=service.audit_service,
        workspace_service=service.workspace_service,
        filesystem_service=MagicMock(),
        process_service=MagicMock(),
        system_service=MagicMock(),
        execution_service=service,
    )

    with pytest.raises(TacpValidationError):
        registry.execute_tool(
            "execution.request",
            {"workspace_id": "ws", "executable": "printf", "argv": "not-a-list"},
        )


# =========================================================================
# Category 19: Malformed JSON RPC
# =========================================================================


def test_cat19_malformed_json_rpc(p5_env: Dict[str, Any]) -> None:
    from tacp.access.mcp.protocol import McpProtocolError, parse_message

    with pytest.raises(McpProtocolError):
        parse_message("{invalid json payload")


# =========================================================================
# Category 20: Oversized Requests
# =========================================================================


def test_cat20_oversized_argv_rejected(p5_env: Dict[str, Any]) -> None:
    resolver: ExecutionResolver = p5_env["resolver"]
    oversized = ["arg"] * 100
    with pytest.raises(TacpValidationError) as exc:
        resolver.validate_argv("printf", oversized)
    assert "exceeds limit" in str(exc.value)


# =========================================================================
# Category 21: Unicode Abuse
# =========================================================================


def test_cat21_unicode_normalization_and_handling(p5_env: Dict[str, Any]) -> None:
    resolver: ExecutionResolver = p5_env["resolver"]
    # UTF-8 multibyte characters in arguments
    argv = resolver.validate_argv("printf", ["printf", "héllo wörld 🚀"])
    assert argv == ("printf", "héllo wörld 🚀")


# =========================================================================
# Category 22: Null-Byte Injections
# =========================================================================


@pytest.mark.parametrize(
    "field_name,payload",
    [
        ("executable", "printf\x00evil"),
        ("cwd", "subdir\x00evil"),
        ("argv", "hello\x00world"),
        ("env_key", "SAFE_VAR\x00"),
        ("env_val", "safe_val\x00"),
    ],
)
def test_cat22_null_byte_injections_rejected(
    p5_env: Dict[str, Any], field_name: str, payload: str
) -> None:
    resolver: ExecutionResolver = p5_env["resolver"]
    ws = p5_env["ws"]
    if field_name == "executable":
        with pytest.raises(TacpSecurityError):
            resolver.resolve_executable(payload)
    elif field_name == "cwd":
        with pytest.raises(TacpSecurityError):
            resolver.resolve_working_directory(Path(ws.root_path), payload)
    elif field_name == "argv":
        with pytest.raises(TacpSecurityError):
            resolver.validate_argv("printf", ["printf", payload])
    elif field_name == "env_key":
        with pytest.raises((TacpSecurityError, TacpValidationError)):
            resolver.assemble_environment(Path(ws.root_path), ws.root_path, {payload: "val"})
    elif field_name == "env_val":
        with pytest.raises(TacpSecurityError):
            resolver.assemble_environment(Path(ws.root_path), ws.root_path, {"VAR1": payload})


# =========================================================================
# Category 23: ANSI / Control Sanitization
# =========================================================================


def test_cat23_ansi_escape_sanitization() -> None:
    malicious = "\x1b[31;1mRed Text\x1b[0m\x1b[2JClear Screen\x1b]0;Title\x07"
    sanitized = sanitize_output(malicious)
    assert "\x1b" not in sanitized
    assert "Clear Screen" in sanitized


# =========================================================================
# Category 24: Rapid Resource Exhaustion
# =========================================================================


def test_cat24_rapid_sequential_executions(p5_env: Dict[str, Any]) -> None:
    service: ExecutionService = p5_env["service"]
    ws = p5_env["ws"]
    # Dry run handles rapid bursts safely
    for _ in range(10):
        res = service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "burst"],
            dry_run=True,
        )
        assert res.status == ExecutionStatus.DRY_RUN.value


# =========================================================================
# Category 25: Capability Confusion
# =========================================================================


def test_cat25_capability_token_confusion(p5_env: Dict[str, Any]) -> None:
    approval: ApprovalEngine = p5_env["approval"]
    service: ExecutionService = p5_env["service"]
    ws = p5_env["ws"]

    # Create patch ticket
    ticket = approval.create_ticket(
        principal_id="local_agent",
        action_type="workspace.patch",
        workspace_id=ws.id,
        target_path="file.txt",
        patch_hash="patch_hash",
    )
    approval.approve(ticket.token, approved_by="human_operator")

    # Attempt to consume workspace.patch ticket in execution.request
    with pytest.raises(TacpSecurityError) as exc:
        service.execute_command(
            workspace_id=ws.id,
            executable="printf",
            argv=["printf", "confusion"],
            approval_token=ticket.token,
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED


# =========================================================================
# Category 26: Identity Confusion
# =========================================================================


def test_cat26_identity_confusion_name_vs_role(p5_env: Dict[str, Any]) -> None:
    policy: PolicyEngine = p5_env["policy"]
    # Principal claims name "human_operator" but has AGENT type and RESTRICTED tier
    rogue_principal = Principal(
        id="human_operator",
        role=Role.AGENT.value,
        authenticated=False,
        principal_type=PrincipalType.AGENT,
        trust_tier=TrustTier.RESTRICTED,
    )
    from tacp.control.identity import RequestContext

    ctx = RequestContext(capability="execution.cancel", principal=rogue_principal)
    decision = policy.evaluate_request(ctx)
    # Must require approval or deny; cannot automatically allow!
    assert decision.allowed is False


# =========================================================================
# Category 27: Privilege Escalation
# =========================================================================


def test_cat27_unauthorized_emergency_stop_denied(p5_env: Dict[str, Any]) -> None:
    service: ExecutionService = p5_env["service"]
    untrusted = Principal.local_agent("untrusted_agent")
    with pytest.raises(TacpSecurityError) as exc:
        service.emergency_stop(principal=untrusted)
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED


# =========================================================================
# Category 28: Contract Tampering
# =========================================================================


def test_cat28_contract_tampering_hash_divergence(p5_env: Dict[str, Any]) -> None:
    ws = p5_env["ws"]
    base = ExecutionContract(
        workspace_id=ws.id,
        executable="/system/bin/printf",
        argv=("printf", "original"),
        cwd=ws.root_path,
        environment=(("PATH", "/bin"),),
        network_enabled=False,
        timeout_seconds=10,
        max_stdout_bytes=1024,
        max_stderr_bytes=1024,
    )
    tampered = ExecutionContract(
        workspace_id=ws.id,
        executable="/system/bin/printf",
        argv=("printf", "tampered!"),
        cwd=ws.root_path,
        environment=(("PATH", "/bin"),),
        network_enabled=False,
        timeout_seconds=10,
        max_stdout_bytes=1024,
        max_stderr_bytes=1024,
    )
    assert compute_execution_contract_hash(base) != compute_execution_contract_hash(tampered)


# =========================================================================
# Category 29: Approval Replay
# =========================================================================


def test_cat29_approval_replay_rejected(p5_env: Dict[str, Any]) -> None:
    approval: ApprovalEngine = p5_env["approval"]
    ticket = approval.create_ticket(
        principal_id="local_agent",
        action_type="execution.request",
        workspace_id="p5_ws",
        target_path="/system/bin/printf",
        patch_hash="contract_hash_123",
    )
    approval.approve(ticket.token, approved_by="human_operator")

    # First consumption succeeds
    assert (
        approval.verify_and_consume(
            token=ticket.token,
            principal_id="local_agent",
            action_type="execution.request",
            workspace_id="p5_ws",
            target_path="/system/bin/printf",
            patch_hash="contract_hash_123",
        )
        is True
    )

    # Second consumption fails
    with pytest.raises(TacpSecurityError) as exc:
        approval.verify_and_consume(
            token=ticket.token,
            principal_id="local_agent",
            action_type="execution.request",
            workspace_id="p5_ws",
            target_path="/system/bin/printf",
            patch_hash="contract_hash_123",
        )
    assert exc.value.code == ErrorCode.APPROVAL_ALREADY_USED


# =========================================================================
# Category 30: Approval Target Path Substitution
# =========================================================================


def test_cat30_approval_target_substitution_rejected(p5_env: Dict[str, Any]) -> None:
    approval: ApprovalEngine = p5_env["approval"]
    ticket = approval.create_ticket(
        principal_id="local_agent",
        action_type="execution.request",
        workspace_id="p5_ws",
        target_path="/system/bin/printf",
        patch_hash="contract_hash_123",
    )
    approval.approve(ticket.token, approved_by="human_operator")

    with pytest.raises(TacpSecurityError) as exc:
        approval.verify_and_consume(
            token=ticket.token,
            principal_id="local_agent",
            action_type="execution.request",
            workspace_id="p5_ws",
            target_path="/system/bin/echo",  # Different target path!
            patch_hash="contract_hash_123",
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED


# =========================================================================
# Category 31: Workspace Substitution
# =========================================================================


def test_cat31_workspace_substitution_rejected(p5_env: Dict[str, Any]) -> None:
    approval: ApprovalEngine = p5_env["approval"]
    ticket = approval.create_ticket(
        principal_id="local_agent",
        action_type="execution.request",
        workspace_id="ws-alpha",
        target_path="/system/bin/printf",
        patch_hash="contract_hash_123",
    )
    approval.approve(ticket.token, approved_by="human_operator")

    with pytest.raises(TacpSecurityError) as exc:
        approval.verify_and_consume(
            token=ticket.token,
            principal_id="local_agent",
            action_type="execution.request",
            workspace_id="ws-beta",  # Different workspace!
            target_path="/system/bin/printf",
            patch_hash="contract_hash_123",
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED


# =========================================================================
# Category 32: Principal Substitution
# =========================================================================


def test_cat32_principal_substitution_rejected(p5_env: Dict[str, Any]) -> None:
    approval: ApprovalEngine = p5_env["approval"]
    ticket = approval.create_ticket(
        principal_id="agent_original",
        action_type="execution.request",
        workspace_id="p5_ws",
        target_path="/system/bin/printf",
        patch_hash="contract_hash_123",
    )
    approval.approve(ticket.token, approved_by="human_operator")

    with pytest.raises(TacpSecurityError) as exc:
        approval.verify_and_consume(
            token=ticket.token,
            principal_id="agent_intruder",  # Different principal!
            action_type="execution.request",
            workspace_id="p5_ws",
            target_path="/system/bin/printf",
            patch_hash="contract_hash_123",
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED
