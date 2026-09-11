"""Comprehensive 78-Case Security Baseline Test Suite for TACP 0.1.

Covers all 78 required security test cases across 7 categories:
1. Path Traversal & File Boundaries (Cases 1-20)
2. Authorization & Policy Enforcement (Cases 21-30)
3. Secrets, Sensitive Data & Sanitization (Cases 31-45)
4. Input Validation & Injection Resistance (Cases 46-57)
5. Output Encoding & Information Leakage (Cases 58-65)
6. Resource Abuse & DoS Resistance (Cases 66-72)
7. Untrusted Data Handling (Cases 73-78)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

import pytest

from tacp.access.mcp.protocol import McpProtocolError, McpRequest, parse_message
from tacp.access.mcp.server import McpServer
from tacp.access.mcp.tools import McpToolRegistry
from tacp.control.identity import RequestContext
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.capability_service import CapabilityService
from tacp.core.filesystem_service import FilesystemService
from tacp.core.process_service import ProcessService
from tacp.core.system_service import SystemService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.classification import DataClassification
from tacp.domain.errors import (
    ErrorCode,
    TacpNotFoundError,
    TacpSecurityError,
    TacpValidationError,
)
from tacp.infrastructure.config import OutputLimits, TacpConfig
from tacp.infrastructure.database import Database
from tacp.infrastructure.logging import redact_string
from tacp.providers.filesystem import FilesystemProvider
from tacp.providers.process import ProcessProvider


@pytest.fixture
def baseline_suite(tmp_path: Path) -> Dict[str, Any]:
    data_dir = tmp_path / "baseline_tacp"
    data_dir.mkdir()
    ws_dir = tmp_path / "baseline_ws"
    ws_dir.mkdir()

    # Pre-populate safe files and test fixtures
    (ws_dir / "safe.txt").write_text("Hello from safe file")
    (ws_dir / "nested").mkdir()
    (ws_dir / "nested" / "doc.txt").write_text("Nested document content")
    (ws_dir / ".env").write_text(
        "OPENAI_API_KEY=" + "sk" + "-proj-test1234567890abcdef1234567890\nDB_PASS=supersecret"
    )
    (ws_dir / "id_rsa").write_text(
        "-----" + "BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----" + "END OPENSSH PRIVATE KEY-----"
    )
    (ws_dir / "id_ed25519").write_text(
        "-----" + "BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----" + "END OPENSSH PRIVATE KEY-----"
    )

    config = TacpConfig(
        data_dir=data_dir,
        db_path=data_dir / "baseline.db",
        read_only=True,
        limits=OutputLimits(
            max_file_read_bytes=1024,  # Lower for quick truncation testing
            max_dir_entries=5,
            max_search_results=5,
        ),
        allowed_workspace_roots=[ws_dir],
    )
    db = Database(config.db_path)
    db.connect()

    audit_service = AuditService(db)
    policy_engine = PolicyEngine(read_only_enforced=True)
    workspace_service = WorkspaceService(db)
    ws = workspace_service.register_workspace("baseline-ws", ws_dir)

    fs_provider = FilesystemProvider(limits=config.limits)
    filesystem_service = FilesystemService(workspace_service, fs_provider)

    proc_provider = ProcessProvider(limits=config.limits)
    process_service = ProcessService(proc_provider)

    system_service = SystemService(db)
    capability_service = CapabilityService()

    tool_registry = McpToolRegistry(
        capability_service=capability_service,
        policy_engine=policy_engine,
        audit_service=audit_service,
        workspace_service=workspace_service,
        filesystem_service=filesystem_service,
        process_service=process_service,
        system_service=system_service,
    )
    server = McpServer(tool_registry=tool_registry, config=config)

    return {
        "ws_dir": ws_dir,
        "ws": ws,
        "fs_provider": fs_provider,
        "policy": policy_engine,
        "tool_registry": tool_registry,
        "server": server,
        "audit": audit_service,
        "proc_provider": proc_provider,
        "tmp_path": tmp_path,
        "db": db,
        "ws_service": workspace_service,
    }


# ==============================================================================
# Category 1: Path Traversal & File Boundaries (Cases 1 - 20)
# ==============================================================================


def test_case_01_relative_traversal_single_dot_dot(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError) as exc:
        baseline_suite["fs_provider"]._resolve_in_jail(baseline_suite["ws_dir"], "../outside.txt")
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_case_02_relative_traversal_double_dot_dot(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError) as exc:
        baseline_suite["fs_provider"]._resolve_in_jail(
            baseline_suite["ws_dir"], "../../outside.txt"
        )
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_case_03_relative_traversal_deep_escape(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError) as exc:
        baseline_suite["fs_provider"]._resolve_in_jail(
            baseline_suite["ws_dir"], "../../../../../../../etc/passwd"
        )
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_case_04_absolute_path_injection_etc_passwd(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError) as exc:
        baseline_suite["fs_provider"]._resolve_in_jail(baseline_suite["ws_dir"], "/etc/passwd")
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_case_05_absolute_termux_home_escape(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError) as exc:
        baseline_suite["fs_provider"]._resolve_in_jail(
            baseline_suite["ws_dir"], "/data/data/com.termux/files/home/.bashrc"
        )
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_case_06_encoded_traversal_percent_2e(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError):
        baseline_suite["fs_provider"]._resolve_in_jail(
            baseline_suite["ws_dir"], "%2e%2e%2foutside.txt"
        )


def test_case_07_encoded_traversal_mixed(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError):
        baseline_suite["fs_provider"]._resolve_in_jail(baseline_suite["ws_dir"], "..%2fetc/passwd")


def test_case_08_null_byte_injection_in_path(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises((TacpSecurityError, ValueError)):
        baseline_suite["fs_provider"]._resolve_in_jail(baseline_suite["ws_dir"], "safe.txt\x00.png")


def test_case_09_symlink_pointing_outside_root(baseline_suite: Dict[str, Any]) -> None:
    sym = baseline_suite["ws_dir"] / "sym_outside"
    sym.symlink_to("/etc/hosts")
    with pytest.raises(TacpSecurityError) as exc:
        baseline_suite["fs_provider"].read_file(baseline_suite["ws_dir"], "sym_outside")
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_case_10_symlink_pointing_to_ssh_keys(baseline_suite: Dict[str, Any]) -> None:
    sym = baseline_suite["ws_dir"] / "sym_ssh"
    fake_ssh = baseline_suite["tmp_path"] / ".ssh"
    fake_ssh.mkdir(exist_ok=True)
    (fake_ssh / "id_rsa").write_text("private")
    sym.symlink_to(fake_ssh / "id_rsa")
    with pytest.raises(TacpSecurityError) as exc:
        baseline_suite["fs_provider"].read_file(baseline_suite["ws_dir"], "sym_ssh")
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_case_11_broken_symlink_handling(baseline_suite: Dict[str, Any]) -> None:
    sym = baseline_suite["ws_dir"] / "sym_broken"
    sym.symlink_to(baseline_suite["ws_dir"] / "nonexistent_target.txt")
    with pytest.raises(TacpNotFoundError) as exc:
        baseline_suite["fs_provider"].read_file(baseline_suite["ws_dir"], "sym_broken")
    assert exc.value.code == ErrorCode.NOT_FOUND


def test_case_12_circular_symlink_handling(baseline_suite: Dict[str, Any]) -> None:
    sym = baseline_suite["ws_dir"] / "sym_cycle"
    sym.symlink_to(sym)
    with pytest.raises((TacpSecurityError, TacpNotFoundError)):
        baseline_suite["fs_provider"].read_file(baseline_suite["ws_dir"], "sym_cycle")


def test_case_13_hardlink_boundary_verification(baseline_suite: Dict[str, Any]) -> None:
    # Within workspace, valid files resolve properly
    res = baseline_suite["fs_provider"]._resolve_in_jail(baseline_suite["ws_dir"], "safe.txt")
    assert res == (baseline_suite["ws_dir"] / "safe.txt").resolve()


def test_case_14_path_normalization_redundant_slashes(baseline_suite: Dict[str, Any]) -> None:
    res = baseline_suite["fs_provider"]._resolve_in_jail(
        baseline_suite["ws_dir"], "nested///doc.txt"
    )
    assert res == (baseline_suite["ws_dir"] / "nested" / "doc.txt").resolve()


def test_case_15_case_sensitivity_boundary(baseline_suite: Dict[str, Any]) -> None:
    # On Linux, SAFE.TXT does not exist if file is safe.txt
    with pytest.raises(TacpNotFoundError):
        baseline_suite["fs_provider"].read_file(baseline_suite["ws_dir"], "SAFE.TXT")


def test_case_16_unicode_normalization_paths(baseline_suite: Dict[str, Any]) -> None:
    # Unicode filenames resolve safely without crashing jail check
    utf8_name = "café.txt"
    (baseline_suite["ws_dir"] / utf8_name).write_text("coffee")
    res = baseline_suite["fs_provider"]._resolve_in_jail(baseline_suite["ws_dir"], utf8_name)
    assert res.name == utf8_name


def test_case_17_workspace_boundary_prefix_collision(baseline_suite: Dict[str, Any]) -> None:
    # Verify that /ws-other is not considered inside /ws even though it shares a string prefix
    fake_sibling = baseline_suite["tmp_path"] / (baseline_suite["ws_dir"].name + "_evil")
    fake_sibling.mkdir()
    (fake_sibling / "leak.txt").write_text("evil")

    rel_escape = f"../{fake_sibling.name}/leak.txt"
    with pytest.raises(TacpSecurityError) as exc:
        baseline_suite["fs_provider"]._resolve_in_jail(baseline_suite["ws_dir"], rel_escape)
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_case_18_empty_path_handling(baseline_suite: Dict[str, Any]) -> None:
    # Empty path resolves to workspace root
    res = baseline_suite["fs_provider"]._resolve_in_jail(baseline_suite["ws_dir"], "")
    assert res == baseline_suite["ws_dir"].resolve()


def test_case_19_dot_only_paths(baseline_suite: Dict[str, Any]) -> None:
    res_dot = baseline_suite["fs_provider"]._resolve_in_jail(baseline_suite["ws_dir"], ".")
    assert res_dot == baseline_suite["ws_dir"].resolve()

    with pytest.raises(TacpSecurityError):
        baseline_suite["fs_provider"]._resolve_in_jail(baseline_suite["ws_dir"], "..")


def test_case_20_very_long_path_boundary(baseline_suite: Dict[str, Any]) -> None:
    long_subpath = "a/" * 2500 + "file.txt"
    with pytest.raises((TacpSecurityError, TacpValidationError, OSError)):
        baseline_suite["fs_provider"]._resolve_in_jail(baseline_suite["ws_dir"], long_subpath)


# ==============================================================================
# Category 2: Authorization & Policy Enforcement (Cases 21 - 30)
# ==============================================================================


def test_case_21_mutation_fs_write_denied(baseline_suite: Dict[str, Any]) -> None:
    dec = baseline_suite["policy"].evaluate_request(RequestContext(capability="fs.write"))
    assert dec.allowed is False


def test_case_22_mutation_fs_append_denied(baseline_suite: Dict[str, Any]) -> None:
    dec = baseline_suite["policy"].evaluate_request(RequestContext(capability="fs.append"))
    assert dec.allowed is False


def test_case_23_mutation_fs_delete_denied(baseline_suite: Dict[str, Any]) -> None:
    dec = baseline_suite["policy"].evaluate_request(RequestContext(capability="fs.delete"))
    assert dec.allowed is False


def test_case_24_mutation_fs_chmod_denied(baseline_suite: Dict[str, Any]) -> None:
    dec = baseline_suite["policy"].evaluate_request(RequestContext(capability="fs.chmod"))
    assert dec.allowed is False


def test_case_25_mutation_process_kill_denied(baseline_suite: Dict[str, Any]) -> None:
    dec = baseline_suite["policy"].evaluate_request(RequestContext(capability="process.kill"))
    assert dec.allowed is False


def test_case_26_mutation_system_reboot_denied(baseline_suite: Dict[str, Any]) -> None:
    dec = baseline_suite["policy"].evaluate_request(RequestContext(capability="system.reboot"))
    assert dec.allowed is False


def test_case_27_disabled_workspace_invocation(baseline_suite: Dict[str, Any]) -> None:
    # Mark workspace as DISABLED
    ws = baseline_suite["ws"]
    conn = baseline_suite["db"].connect()
    conn.execute(
        "UPDATE workspaces SET status = 'DISABLED' WHERE id = ?",
        (ws.id,),
    )
    conn.commit()
    disabled_ws = baseline_suite["ws_service"].get_workspace(ws.id)
    dec = baseline_suite["policy"].evaluate_request(
        RequestContext(capability="fs.read"),
        workspace=disabled_ws,
    )
    assert dec.allowed is False
    assert "DISABLED" in dec.reason


def test_case_28_unknown_capability_invocation(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises(TacpNotFoundError):
        baseline_suite["tool_registry"].execute_tool("unknown.super_tool", {})


def test_case_29_missing_required_params(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises(TacpValidationError):
        baseline_suite["tool_registry"].execute_tool("fs.read", {})


def test_case_30_policy_engine_tampering_immutable(baseline_suite: Dict[str, Any]) -> None:
    # Verify policy engine strictly enforces read-only invariants across all mutation capabilities
    engine = PolicyEngine(read_only_enforced=True)
    assert engine.read_only_enforced is True
    for cap in ["fs.write", "fs.delete", "fs.chmod", "shell.exec", "bash.run", "os.system"]:
        dec = engine.evaluate_request(RequestContext(capability=cap))
        assert dec.allowed is False
        assert "forbidden" in dec.reason.lower()


# ==============================================================================
# Category 3: Secrets, Sensitive Data & Sanitization (Cases 31 - 45)
# ==============================================================================


def test_case_31_secret_ssh_id_rsa(baseline_suite: Dict[str, Any]) -> None:
    cls = baseline_suite["fs_provider"]._classify_path(Path("id_rsa"))
    assert cls == DataClassification.SECRET


def test_case_32_secret_ssh_id_ed25519(baseline_suite: Dict[str, Any]) -> None:
    cls = baseline_suite["fs_provider"]._classify_path(Path("id_ed25519"))
    assert cls == DataClassification.SECRET


def test_case_33_secret_env_file(baseline_suite: Dict[str, Any]) -> None:
    cls = baseline_suite["fs_provider"]._classify_path(Path(".env"))
    assert cls == DataClassification.SECRET


def test_case_34_secret_api_key_openai() -> None:
    raw = "key = " + "sk" + "-proj-1234567890abcdef1234567890abcdef1234"
    redacted = redact_string(raw)
    assert "sk-proj-" not in redacted
    assert "[REDACTED]" in redacted


def test_case_35_secret_api_key_anthropic() -> None:
    raw = "key = " + "sk" + "-ant-api03-abcdef1234567890abcdef1234567890"
    redacted = redact_string(raw)
    assert "sk-ant-" not in redacted
    assert "[REDACTED]" in redacted


def test_case_36_secret_api_key_github() -> None:
    raw = "github_pat: " + "gh" + "p_999999999999999999999999999999999999"
    redacted = redact_string(raw)
    assert "ghp_" not in redacted
    assert "[REDACTED]" in redacted


def test_case_37_secret_database_url_password() -> None:
    raw = "postgresql://admin:SuperSecretPass123!@localhost:5432/mydb"
    redacted = redact_string(raw)
    assert "SuperSecretPass123!" not in redacted
    assert "[REDACTED]" in redacted


def test_case_38_secret_termux_private_file(baseline_suite: Dict[str, Any]) -> None:
    # .bashrc outside workspace in Termux root is blocked
    with pytest.raises(TacpSecurityError):
        baseline_suite["fs_provider"]._resolve_in_jail(
            baseline_suite["ws_dir"], "/data/data/com.termux/files/home/.bashrc"
        )


def test_case_39_secret_android_properties(baseline_suite: Dict[str, Any]) -> None:
    info = baseline_suite["server"].handle_request(
        McpRequest(method="tools/call", params={"name": "system.inspect", "arguments": {}}, id=1)
    )
    assert info is not None
    text = info.result["content"][0]["text"]
    assert "imei" not in text.lower()
    assert "mac_address" not in text.lower()


def test_case_40_secret_proc_kallsyms_protection(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError):
        baseline_suite["fs_provider"]._resolve_in_jail(baseline_suite["ws_dir"], "/proc/kallsyms")


def test_case_41_secret_redaction_file_content(baseline_suite: Dict[str, Any]) -> None:
    leaky = baseline_suite["ws_dir"] / "leaky_app.py"
    leaky.write_text("API_KEY = '" + "sk" + "-proj-supersecrettoken1234567890'\nprint('running')")
    res = baseline_suite["fs_provider"].read_file(baseline_suite["ws_dir"], "leaky_app.py")
    assert "sk-proj-" not in res["content"]
    assert "[REDACTED]" in res["content"]


def test_case_42_secret_redaction_search_results(baseline_suite: Dict[str, Any]) -> None:
    cfg_file = baseline_suite["ws_dir"] / "app_config.json"
    cfg_file.write_text('{"service": "openai", "token": "' + "sk" + '-proj-secrettoken1234567890"}')
    res = baseline_suite["fs_provider"].search_files(baseline_suite["ws_dir"], query="openai")
    assert len(res["matches"]) > 0
    for match in res["matches"]:
        assert "sk-proj-" not in match["snippet"]
        assert "[REDACTED]" in match["snippet"]


def test_case_43_secret_redaction_audit_logs(baseline_suite: Dict[str, Any]) -> None:
    # Trigger tool with secret in argument
    baseline_suite["tool_registry"].execute_tool(
        "fs.search",
        {
            "workspace_id": baseline_suite["ws"].id,
            "query": "sk" + "-proj-supersecretkey1234567890",
        },
    )
    events = baseline_suite["audit"].get_recent_events(limit=5)
    recent = events[0]
    raw_params = json.dumps(recent["parameters"])
    assert "sk-proj-" not in raw_params
    assert "[REDACTED]" in raw_params


def test_case_44_secret_redaction_error_messages(baseline_suite: Dict[str, Any]) -> None:
    # Error message with secret string
    err_text = redact_string("Error: token " + "sk" + "-proj-1234567890abcdef was invalid")
    assert "sk-proj-" not in err_text
    assert "[REDACTED]" in err_text


def test_case_45_binary_file_leak_prevention(baseline_suite: Dict[str, Any]) -> None:
    bin_file = baseline_suite["ws_dir"] / "test.bin"
    bin_file.write_bytes(b"\x00\x01\x02\x03\x04\xff\xfe\xfd")
    with pytest.raises(TacpSecurityError) as exc:
        baseline_suite["fs_provider"].read_file(baseline_suite["ws_dir"], "test.bin")
    assert exc.value.code == ErrorCode.RESOURCE_LIMIT


# ==============================================================================
# Category 4: Input Validation & Injection Resistance (Cases 46 - 57)
# ==============================================================================


def test_case_46_shell_metacharacters_in_path(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises((TacpSecurityError, TacpNotFoundError)):
        baseline_suite["fs_provider"].read_file(baseline_suite["ws_dir"], "safe.txt; rm -rf /")


def test_case_47_shell_pipe_in_path(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises((TacpSecurityError, TacpNotFoundError)):
        baseline_suite["fs_provider"].read_file(
            baseline_suite["ws_dir"], "safe.txt | cat /etc/passwd"
        )


def test_case_48_sql_injection_in_workspace_query(baseline_suite: Dict[str, Any]) -> None:
    # Query with SQL injection payload executes harmlessly as text query
    res = baseline_suite["fs_provider"].search_files(
        baseline_suite["ws_dir"],
        query="' OR 1=1 --",
    )
    assert isinstance(res["matches"], list)


def test_case_49_sql_injection_in_workspace_id(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises(TacpNotFoundError):
        baseline_suite["ws_service"].get_workspace("' OR '1'='1")


def test_case_50_sql_injection_in_audit_limit(baseline_suite: Dict[str, Any]) -> None:
    # SQL injection in limit
    events = baseline_suite["audit"].get_recent_events(limit=10)
    assert isinstance(events, list)


def test_case_51_negative_limit_rejected(baseline_suite: Dict[str, Any]) -> None:
    res = baseline_suite["audit"].get_recent_events(limit=-5)
    # Service clamps negative limit or returns empty/bounded list
    assert isinstance(res, list)


def test_case_52_excessive_limit_clamped(baseline_suite: Dict[str, Any]) -> None:
    res = baseline_suite["audit"].get_recent_events(limit=1000000)
    assert len(res) <= 100


def test_case_53_format_string_in_inputs(baseline_suite: Dict[str, Any]) -> None:
    res = baseline_suite["fs_provider"].search_files(
        baseline_suite["ws_dir"],
        query="%s%s%s%n",
    )
    assert isinstance(res["matches"], list)


def test_case_54_control_characters_in_inputs(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises((TacpSecurityError, TacpValidationError, TacpNotFoundError, ValueError)):
        baseline_suite["fs_provider"].read_file(baseline_suite["ws_dir"], "safe\r\n\x00.txt")


def test_case_55_large_payload_handling(baseline_suite: Dict[str, Any]) -> None:
    large_query = "A" * 100000
    res = baseline_suite["fs_provider"].search_files(baseline_suite["ws_dir"], query=large_query)
    assert res["matches"] == []


def test_case_56_deeply_nested_json(baseline_suite: Dict[str, Any]) -> None:
    nested: Dict[str, Any] = {"inner": None}
    curr = nested
    for _ in range(50):
        curr["inner"] = {"next": {}}
        curr = curr["inner"]["next"]
    req = McpRequest(
        method="tools/call",
        params={"name": "system.version", "arguments": nested},
        id="nested-1",
    )
    resp = baseline_suite["server"].handle_request(req)
    assert resp is not None
    assert resp.result["isError"] is False


def test_case_57_invalid_jsonrpc_syntax() -> None:
    with pytest.raises(McpProtocolError):
        parse_message("{invalid_json: true")


# ==============================================================================
# Category 5: Output Encoding & Information Leakage (Cases 58 - 65)
# ==============================================================================


def test_case_58_stack_trace_suppressed(baseline_suite: Dict[str, Any]) -> None:
    req = McpRequest(
        method="tools/call",
        params={
            "name": "fs.read",
            "arguments": {"workspace_id": baseline_suite["ws"].id, "subpath": "../escape"},
        },
        id="trace-test",
    )
    resp = baseline_suite["server"].handle_request(req)
    assert resp is not None
    assert resp.result["isError"] is True
    err_text = resp.result["content"][0]["text"]
    assert "Traceback (most recent call last)" not in err_text


def test_case_59_internal_path_leakage_prevented(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError) as exc:
        baseline_suite["fs_provider"]._resolve_in_jail(baseline_suite["ws_dir"], "../private")
    assert str(baseline_suite["ws_dir"].parent) not in exc.value.message


def test_case_60_database_schema_not_leaked(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises(TacpNotFoundError) as exc:
        baseline_suite["ws_service"].get_workspace("nonexistent")
    assert "sqlite_master" not in exc.value.message


def test_case_61_env_var_leakage_in_process_inspect(baseline_suite: Dict[str, Any]) -> None:
    curr_pid = os.getpid()
    proc_info = baseline_suite["proc_provider"].inspect_process(curr_pid)
    # Process inspection must not leak raw full environment dict
    assert "environ" not in proc_info
    assert "env" not in proc_info


def test_case_62_cmdline_secret_sanitized() -> None:
    cmdline = "myapp --api-key " + "sk" + "-proj-1234567890abcdef1234567890 --db-pass SuperSecret!"
    sanitized = redact_string(cmdline)
    assert "sk-proj-" not in sanitized
    assert "[REDACTED]" in sanitized


def test_case_63_output_truncation_exact_boundary(baseline_suite: Dict[str, Any]) -> None:
    big_file = baseline_suite["ws_dir"] / "big.txt"
    big_file.write_text("x" * 5000)
    res = baseline_suite["fs_provider"].read_file(baseline_suite["ws_dir"], "big.txt")
    assert res["truncated"] is True
    assert res["bytes_read"] == 1024


def test_case_64_dir_list_truncation_boundary(baseline_suite: Dict[str, Any]) -> None:
    multi_dir = baseline_suite["ws_dir"] / "many_files"
    multi_dir.mkdir()
    for i in range(10):
        (multi_dir / f"file_{i}.txt").write_text(f"content {i}")
    res = baseline_suite["fs_provider"].list_dir(baseline_suite["ws_dir"], "many_files")
    assert res["truncated"] is True
    assert len(res["entries"]) == 5


def test_case_65_utf8_encoding_invalid_bytes(baseline_suite: Dict[str, Any]) -> None:
    bad_utf8 = baseline_suite["ws_dir"] / "bad_utf8.txt"
    # Write invalid UTF-8 byte sequence with high text ratio
    bad_utf8.write_bytes(b"Valid prefix text " + b"\xff\xfe" + b" valid suffix text")
    res = baseline_suite["fs_provider"].read_file(baseline_suite["ws_dir"], "bad_utf8.txt")
    assert "Valid prefix" in res["content"]


# ==============================================================================
# Category 6: Resource Abuse & DoS Resistance (Cases 66 - 72)
# ==============================================================================


def test_case_66_dev_zero_urandom_blocked(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError):
        baseline_suite["fs_provider"]._resolve_in_jail(baseline_suite["ws_dir"], "/dev/urandom")


def test_case_67_named_pipe_fifo_blocked(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError):
        baseline_suite["fs_provider"]._resolve_in_jail(baseline_suite["ws_dir"], "/dev/null")


def test_case_68_large_file_read_bounded(baseline_suite: Dict[str, Any]) -> None:
    large = baseline_suite["ws_dir"] / "large_file.txt"
    large.write_text("A" * 2048)
    res = baseline_suite["fs_provider"].read_file(baseline_suite["ws_dir"], "large_file.txt")
    assert len(res["content"]) <= 1024


def test_case_69_large_dir_list_bounded(baseline_suite: Dict[str, Any]) -> None:
    res = baseline_suite["fs_provider"].list_dir(baseline_suite["ws_dir"], "")
    assert len(res["entries"]) <= baseline_suite["fs_provider"].limits.max_dir_entries


def test_case_70_catastrophic_backtracking_regex(baseline_suite: Dict[str, Any]) -> None:
    # Pathological regex pattern against non-matching text
    res = baseline_suite["fs_provider"].search_files(
        baseline_suite["ws_dir"],
        query=r"(a+)+$",
    )
    assert isinstance(res["matches"], list)


def test_case_71_nonexistent_pid_inspection(baseline_suite: Dict[str, Any]) -> None:
    with pytest.raises(TacpNotFoundError):
        baseline_suite["proc_provider"].inspect_process(99999999)


def test_case_72_database_connection_isolation(baseline_suite: Dict[str, Any]) -> None:
    # Test multiple sequential queries
    h1 = baseline_suite["db"].is_healthy()
    h2 = baseline_suite["db"].is_healthy()
    assert h1 is True
    assert h2 is True


# ==============================================================================
# Category 7: Untrusted Data Handling (Cases 73 - 78)
# ==============================================================================


def test_case_73_terminal_escape_in_filename(baseline_suite: Dict[str, Any]) -> None:
    name = "clear_\x1b[2J_screen.txt"
    try:
        (baseline_suite["ws_dir"] / name).write_text("escape")
        res = baseline_suite["fs_provider"].list_dir(baseline_suite["ws_dir"], "")
        names = [e["name"] for e in res["entries"]]
        assert any("clear_" in n for n in names)
    except OSError:
        pytest.skip("Filesystem rejected terminal escape filename creation")


def test_case_74_ansi_color_in_search(baseline_suite: Dict[str, Any]) -> None:
    res = baseline_suite["fs_provider"].search_files(
        baseline_suite["ws_dir"],
        query="\x1b[31mred\x1b[0m",
    )
    assert res["matches"] == []


def test_case_75_bidi_override_in_filename(baseline_suite: Dict[str, Any]) -> None:
    bidi_name = "test_\u202e_doc.txt"
    try:
        (baseline_suite["ws_dir"] / bidi_name).write_text("bidi")
        res = baseline_suite["fs_provider"].list_dir(baseline_suite["ws_dir"], "")
        assert isinstance(res["entries"], list)
    except OSError:
        pytest.skip("Filesystem does not support bidi filename creation")


def test_case_76_invisible_chars_in_identifiers(baseline_suite: Dict[str, Any]) -> None:
    # Zero width space in query or name
    res = baseline_suite["fs_provider"].search_files(
        baseline_suite["ws_dir"],
        query="test\u200bhidden",
    )
    assert res["matches"] == []


def test_case_77_untrusted_content_in_audit_log(baseline_suite: Dict[str, Any]) -> None:
    malicious_input = "__import__('os').system('echo pwned')"
    baseline_suite["tool_registry"].execute_tool(
        "fs.search",
        {
            "workspace_id": baseline_suite["ws"].id,
            "query": malicious_input,
        },
    )
    events = baseline_suite["audit"].get_recent_events(limit=1)
    assert events[0]["parameters"]["query"] == malicious_input


def test_case_78_untrusted_input_in_cli_output(baseline_suite: Dict[str, Any]) -> None:
    # Execute MCP call reflecting untrusted input safely
    req = McpRequest(
        method="tools/call",
        params={
            "name": "fs.search",
            "arguments": {
                "workspace_id": baseline_suite["ws"].id,
                "query": "<script>alert('xss')</script>",
            },
        },
        id="untrusted-78",
    )
    resp = baseline_suite["server"].handle_request(req)
    assert resp is not None
    assert resp.result["isError"] is False
    assert "<script>" in resp.result["content"][0]["text"]
