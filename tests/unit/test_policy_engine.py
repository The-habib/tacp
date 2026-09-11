"""Tests for Policy Engine and Default-Deny Invariants (Category G)."""

from pathlib import Path

import pytest

from tacp.control.identity import Principal, RequestContext
from tacp.control.policy import PolicyEngine
from tacp.domain.errors import ErrorCode, TacpSecurityError
from tacp.domain.workspace import Workspace


@pytest.fixture
def policy_engine() -> PolicyEngine:
    return PolicyEngine(read_only_enforced=True)


@pytest.fixture
def active_workspace(tmp_path: Path) -> Workspace:
    return Workspace(
        id="ws-test",
        name="test",
        root_path=tmp_path,
        status="ACTIVE",
    )


def test_allowed_all_13_readonly_capabilities(
    policy_engine: PolicyEngine, active_workspace: Workspace
) -> None:
    expected_caps = [
        "system.inspect",
        "system.health",
        "system.version",
        "capabilities.list",
        "workspace.list",
        "workspace.inspect",
        "fs.list",
        "fs.stat",
        "fs.read",
        "fs.search",
        "process.list",
        "process.inspect",
        "audit.recent",
    ]
    for cap in expected_caps:
        ctx = RequestContext(capability=cap, principal=Principal(id="agent"))
        decision = policy_engine.evaluate_request(ctx, workspace=active_workspace)
        assert decision.allowed is True
        assert decision.requires_audit is True


def test_default_deny_unknown_capability(
    policy_engine: PolicyEngine, active_workspace: Workspace
) -> None:
    ctx = RequestContext(capability="random.operation", principal=Principal(id="agent"))
    decision = policy_engine.evaluate_request(ctx, workspace=active_workspace)
    assert decision.allowed is False
    assert "not recognized or forbidden" in decision.reason


def test_deny_shell_execution(policy_engine: PolicyEngine) -> None:
    for forbidden in ["shell.exec", "bash.run", "exec.command", "os.system"]:
        ctx = RequestContext(capability=forbidden)
        decision = policy_engine.evaluate_request(ctx)
        assert decision.allowed is False


def test_deny_fs_write_operations(policy_engine: PolicyEngine) -> None:
    for forbidden in ["fs.write", "fs.create", "fs.append", "fs.modify"]:
        ctx = RequestContext(capability=forbidden)
        decision = policy_engine.evaluate_request(ctx)
        assert decision.allowed is False


def test_deny_fs_delete_operations(policy_engine: PolicyEngine) -> None:
    for forbidden in ["fs.delete", "fs.unlink", "fs.remove", "fs.rmdir"]:
        ctx = RequestContext(capability=forbidden)
        decision = policy_engine.evaluate_request(ctx)
        assert decision.allowed is False


def test_deny_android_device_control(policy_engine: PolicyEngine) -> None:
    for forbidden in ["android.intent", "android.broadcast", "android.sms", "android.call"]:
        ctx = RequestContext(capability=forbidden)
        decision = policy_engine.evaluate_request(ctx)
        assert decision.allowed is False


def test_deny_root_and_adb_elevation(policy_engine: PolicyEngine) -> None:
    for forbidden in ["root.escalate", "adb.command", "shizuku.exec", "su.exec"]:
        ctx = RequestContext(capability=forbidden)
        decision = policy_engine.evaluate_request(ctx)
        assert decision.allowed is False


def test_deny_suspended_workspace(policy_engine: PolicyEngine, tmp_path: Path) -> None:
    ws = Workspace(id="ws-suspended", name="suspended", root_path=tmp_path, status="SUSPENDED")
    ctx = RequestContext(capability="fs.read")
    decision = policy_engine.evaluate_request(ctx, workspace=ws)
    assert decision.allowed is False
    assert "not ACTIVE" in decision.reason


def test_deny_revoked_workspace(policy_engine: PolicyEngine, tmp_path: Path) -> None:
    ws = Workspace(id="ws-revoked", name="revoked", root_path=tmp_path, status="REVOKED")
    ctx = RequestContext(capability="fs.list")
    decision = policy_engine.evaluate_request(ctx, workspace=ws)
    assert decision.allowed is False
    assert "not ACTIVE" in decision.reason


def test_check_or_raise_allowed(policy_engine: PolicyEngine, active_workspace: Workspace) -> None:
    ctx = RequestContext(capability="fs.read")
    policy_engine.check_or_raise(ctx, workspace=active_workspace)


def test_check_or_raise_denied_raises_security_error(policy_engine: PolicyEngine) -> None:
    ctx = RequestContext(capability="shell.exec")
    with pytest.raises(TacpSecurityError) as exc_info:
        policy_engine.check_or_raise(ctx)
    assert exc_info.value.code == ErrorCode.NOT_AUTHORIZED
