"""40 Required Security Test Cases for TACP 0.1 Verification Baseline."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

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
from tacp.domain.errors import ErrorCode, TacpNotFoundError, TacpSecurityError, TacpValidationError
from tacp.infrastructure.config import OutputLimits, TacpConfig
from tacp.infrastructure.database import Database
from tacp.infrastructure.logging import redact_string
from tacp.providers.filesystem import FilesystemProvider
from tacp.providers.process import ProcessProvider


@pytest.fixture
def sec_suite(tmp_path: Path) -> dict[str, Any]:
    data_dir = tmp_path / "sec_tacp"
    data_dir.mkdir()
    ws_dir = tmp_path / "sec_ws"
    ws_dir.mkdir()

    (ws_dir / "safe.txt").write_text("safe content")
    (ws_dir / "secret.env").write_text("API_KEY=sk-test12345")
    (ws_dir / "id_rsa").write_text("-----" + "BEGIN RSA PRIVATE KEY-----")

    config = TacpConfig(
        data_dir=data_dir,
        db_path=data_dir / "sec.db",
        read_only=True,
        limits=OutputLimits(),
        allowed_workspace_roots=[ws_dir],
    )
    db = Database(config.db_path)
    db.connect()

    audit_service = AuditService(db)
    policy_engine = PolicyEngine(read_only_enforced=True)
    workspace_service = WorkspaceService(db)
    ws = workspace_service.register_workspace("sec-ws", ws_dir)

    fs_provider = FilesystemProvider(limits=config.limits)
    filesystem_service = FilesystemService(workspace_service, fs_provider)

    proc_provider = ProcessProvider(limits=config.limits)
    process_service = ProcessService(proc_provider)

    system_service = SystemService(db)
    capability_service = CapabilityService()

    tools = McpToolRegistry(
        capability_service=capability_service,
        policy_engine=policy_engine,
        audit_service=audit_service,
        workspace_service=workspace_service,
        filesystem_service=filesystem_service,
        process_service=process_service,
        system_service=system_service,
    )

    return {
        "ws_dir": ws_dir,
        "ws": ws,
        "fs_provider": fs_provider,
        "policy": policy_engine,
        "tools": tools,
        "audit": audit_service,
        "proc_provider": proc_provider,
        "tmp_path": tmp_path,
    }


# 1. Path Traversal Attacks
def test_sec_01_traversal_single_parent(sec_suite: dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError) as exc:
        sec_suite["fs_provider"]._resolve_in_jail(sec_suite["ws_dir"], "../outside.txt")
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_sec_02_traversal_double_parent(sec_suite: dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError) as exc:
        sec_suite["fs_provider"]._resolve_in_jail(sec_suite["ws_dir"], "../../outside.txt")
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_sec_03_traversal_deep_passwd(sec_suite: dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError) as exc:
        sec_suite["fs_provider"]._resolve_in_jail(
            sec_suite["ws_dir"], "../../../../../../etc/passwd"
        )
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_sec_04_traversal_absolute_shadow(sec_suite: dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError) as exc:
        sec_suite["fs_provider"]._resolve_in_jail(sec_suite["ws_dir"], "/etc/shadow")
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_sec_05_traversal_absolute_proc(sec_suite: dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError) as exc:
        sec_suite["fs_provider"]._resolve_in_jail(sec_suite["ws_dir"], "/proc/1/cmdline")
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_sec_06_traversal_encoded_dots(sec_suite: dict[str, Any]) -> None:
    # URL encoded dots should not slip through
    with pytest.raises(TacpSecurityError):
        sec_suite["fs_provider"]._resolve_in_jail(sec_suite["ws_dir"], "..%2f..%2fetc/passwd")


def test_sec_07_traversal_null_byte_injection(sec_suite: dict[str, Any]) -> None:
    with pytest.raises((TacpSecurityError, ValueError)):
        sec_suite["fs_provider"]._resolve_in_jail(sec_suite["ws_dir"], "safe.txt\x00/../etc/passwd")


def test_sec_08_traversal_multiple_slashes(sec_suite: dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError):
        sec_suite["fs_provider"]._resolve_in_jail(sec_suite["ws_dir"], "////etc/shadow")


def test_sec_09_traversal_nested_dot_dot_in_middle(sec_suite: dict[str, Any]) -> None:
    with pytest.raises(TacpSecurityError):
        sec_suite["fs_provider"]._resolve_in_jail(
            sec_suite["ws_dir"], "sub/../../../../../../etc/passwd"
        )


# 2. Symlink Attacks
def test_sec_10_symlink_pointing_to_etc_passwd(sec_suite: dict[str, Any]) -> None:
    sym = sec_suite["ws_dir"] / "evil_passwd"
    sym.symlink_to("/etc/passwd")
    with pytest.raises(TacpSecurityError) as exc:
        sec_suite["fs_provider"].read_file(sec_suite["ws_dir"], "evil_passwd")
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_sec_11_symlink_pointing_to_parent_dir(sec_suite: dict[str, Any]) -> None:
    sym = sec_suite["ws_dir"] / "evil_parent"
    sym.symlink_to(sec_suite["ws_dir"].parent)
    with pytest.raises(TacpSecurityError) as exc:
        sec_suite["fs_provider"].list_dir(sec_suite["ws_dir"], "evil_parent")
    assert exc.value.code == ErrorCode.OUTSIDE_WORKSPACE


def test_sec_12_symlink_chain_escaping(sec_suite: dict[str, Any], tmp_path: Path) -> None:
    outside = tmp_path / "outside_target.txt"
    outside.write_text("secret outside")
    sym1 = sec_suite["ws_dir"] / "sym1"
    sym1.symlink_to(outside)
    with pytest.raises(TacpSecurityError):
        sec_suite["fs_provider"].read_file(sec_suite["ws_dir"], "sym1")


def test_sec_13_symlink_stat_resolves_and_validates(sec_suite: dict[str, Any]) -> None:
    sym = sec_suite["ws_dir"] / "sym_stat"
    sym.symlink_to("/etc/hosts")
    with pytest.raises(TacpSecurityError):
        sec_suite["fs_provider"].stat_path(sec_suite["ws_dir"], "sym_stat")


def test_sec_14_symlink_search_does_not_escape(sec_suite: dict[str, Any]) -> None:
    sym = sec_suite["ws_dir"] / "sym_search"
    sym.symlink_to("/etc")
    with pytest.raises(TacpSecurityError):
        sec_suite["fs_provider"].search_files(
            sec_suite["ws_dir"], query="root", subpath="sym_search"
        )


# 3. Binary & Resource Limit Defenses
def test_sec_15_binary_file_read_blocked(sec_suite: dict[str, Any]) -> None:
    bin_f = sec_suite["ws_dir"] / "binary.bin"
    bin_f.write_bytes(b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00")
    with pytest.raises(TacpSecurityError) as exc:
        sec_suite["fs_provider"].read_file(sec_suite["ws_dir"], "binary.bin")
    assert exc.value.code == ErrorCode.RESOURCE_LIMIT


# 4. Secret File Classification
def test_sec_16_classify_env_file(sec_suite: dict[str, Any]) -> None:
    assert sec_suite["fs_provider"]._classify_path(Path(".env")) == DataClassification.SECRET


def test_sec_17_classify_env_local_file(sec_suite: dict[str, Any]) -> None:
    assert sec_suite["fs_provider"]._classify_path(Path(".env.local")) == DataClassification.SECRET


def test_sec_18_classify_id_rsa(sec_suite: dict[str, Any]) -> None:
    assert sec_suite["fs_provider"]._classify_path(Path("id_rsa")) == DataClassification.SECRET


def test_sec_19_classify_id_ed25519(sec_suite: dict[str, Any]) -> None:
    assert sec_suite["fs_provider"]._classify_path(Path("id_ed25519")) == DataClassification.SECRET


def test_sec_20_classify_credentials_json(sec_suite: dict[str, Any]) -> None:
    cls = sec_suite["fs_provider"]._classify_path(Path("credentials.json"))
    assert cls == DataClassification.SECRET


# 5. Secret Content Redaction
def test_sec_21_redact_bearer_token() -> None:
    raw = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret"
    assert "[REDACTED]" in redact_string(raw)


def test_sec_22_redact_github_pat() -> None:
    raw = "token: " + "gh" + "p_123456789012345678901234567890123456"
    assert "ghp_" not in redact_string(raw)
    assert "[REDACTED]" in redact_string(raw)


def test_sec_23_redact_anthropic_key() -> None:
    raw = "sk" + "-ant-api03-1234567890abcdef1234567890"
    assert "sk-ant-" not in redact_string(raw)


def test_sec_24_redact_openai_key() -> None:
    raw = "sk" + "-1234567890abcdef1234567890abcdef1234"
    assert "sk-" not in redact_string(raw)


def test_sec_25_redact_private_key_header() -> None:
    raw = "-----" + "BEGIN RSA PRIVATE KEY-----\ncontent\n-----" + "END RSA PRIVATE KEY-----"
    assert "RSA PRIVATE KEY" not in redact_string(raw)


# 6. Policy Engine Forbidden Operations
def test_sec_26_deny_fs_write(sec_suite: dict[str, Any]) -> None:
    decision = sec_suite["policy"].evaluate_request(RequestContext(capability="fs.write"))
    assert decision.allowed is False


def test_sec_27_deny_fs_delete(sec_suite: dict[str, Any]) -> None:
    decision = sec_suite["policy"].evaluate_request(RequestContext(capability="fs.delete"))
    assert decision.allowed is False


def test_sec_28_deny_fs_chmod(sec_suite: dict[str, Any]) -> None:
    decision = sec_suite["policy"].evaluate_request(RequestContext(capability="fs.chmod"))
    assert decision.allowed is False


def test_sec_29_deny_shell_exec(sec_suite: dict[str, Any]) -> None:
    decision = sec_suite["policy"].evaluate_request(RequestContext(capability="shell.exec"))
    assert decision.allowed is False


def test_sec_30_deny_bash_run(sec_suite: dict[str, Any]) -> None:
    decision = sec_suite["policy"].evaluate_request(RequestContext(capability="bash.run"))
    assert decision.allowed is False


def test_sec_31_deny_os_system(sec_suite: dict[str, Any]) -> None:
    decision = sec_suite["policy"].evaluate_request(RequestContext(capability="os.system"))
    assert decision.allowed is False


def test_sec_32_deny_android_intent(sec_suite: dict[str, Any]) -> None:
    decision = sec_suite["policy"].evaluate_request(RequestContext(capability="android.intent"))
    assert decision.allowed is False


def test_sec_33_deny_android_sms(sec_suite: dict[str, Any]) -> None:
    decision = sec_suite["policy"].evaluate_request(RequestContext(capability="android.sms"))
    assert decision.allowed is False


def test_sec_34_deny_android_notify(sec_suite: dict[str, Any]) -> None:
    decision = sec_suite["policy"].evaluate_request(RequestContext(capability="android.notify"))
    assert decision.allowed is False


def test_sec_35_deny_adb_command(sec_suite: dict[str, Any]) -> None:
    decision = sec_suite["policy"].evaluate_request(RequestContext(capability="adb.command"))
    assert decision.allowed is False


def test_sec_36_deny_shizuku_exec(sec_suite: dict[str, Any]) -> None:
    decision = sec_suite["policy"].evaluate_request(RequestContext(capability="shizuku.exec"))
    assert decision.allowed is False


def test_sec_37_deny_root_escalate(sec_suite: dict[str, Any]) -> None:
    decision = sec_suite["policy"].evaluate_request(RequestContext(capability="root.escalate"))
    assert decision.allowed is False


# 7. Process & Isolation Defenses
def test_sec_38_inspect_foreign_uid_pid_denied(sec_suite: dict[str, Any]) -> None:
    mock_stat = MagicMock()
    mock_stat.st_uid = 0  # Foreign UID
    with patch("pathlib.Path.stat", return_value=mock_stat):
        with patch("pathlib.Path.exists", return_value=True):
            with pytest.raises(TacpSecurityError) as exc:
                sec_suite["proc_provider"].inspect_process(1)
            assert exc.value.code == ErrorCode.NOT_AUTHORIZED


def test_sec_39_negative_pid_rejected(sec_suite: dict[str, Any]) -> None:
    with pytest.raises(TacpValidationError) as exc:
        sec_suite["proc_provider"].inspect_process(-99)
    assert exc.value.code == ErrorCode.INVALID_INPUT


def test_sec_40_nonexistent_workspace_denied(sec_suite: dict[str, Any]) -> None:
    with pytest.raises(TacpNotFoundError) as exc:
        sec_suite["tools"].execute_tool(
            "fs.read",
            {"workspace_id": "nonexistent_ws_id", "subpath": "safe.txt"},
        )
    assert exc.value.code == ErrorCode.NOT_FOUND
