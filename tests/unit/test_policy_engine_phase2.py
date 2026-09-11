"""Unit tests for Policy Engine Phase 2 additions (Category G & M)."""

from pathlib import Path

import pytest

from tacp.control.identity import Principal, RequestContext
from tacp.control.policy import PolicyEngine
from tacp.domain.errors import TacpApprovalRequiredError
from tacp.domain.workspace import Workspace


@pytest.fixture
def active_ws(tmp_path: Path) -> Workspace:
    return Workspace(
        id="ws-active",
        name="active",
        root_path=tmp_path,
        status="ACTIVE",
    )


@pytest.fixture
def suspended_ws(tmp_path: Path) -> Workspace:
    return Workspace(
        id="ws-suspended",
        name="suspended",
        root_path=tmp_path,
        status="SUSPENDED",
    )


def test_mutation_disabled_by_default(active_ws: Workspace) -> None:
    pe = PolicyEngine(mutation_enabled=False)
    ctx = RequestContext(capability="workspace.patch", principal=Principal(id="agent"))
    decision = pe.evaluate_request(ctx, workspace=active_ws)
    assert decision.allowed is False
    assert decision.decision_type == "DENY"
    assert "mutation is disabled" in decision.reason


def test_dry_run_allowed_without_approval(active_ws: Workspace) -> None:
    pe = PolicyEngine(mutation_enabled=True)
    ctx = RequestContext(capability="workspace.patch", principal=Principal(id="agent"))
    decision = pe.evaluate_request(
        ctx, workspace=active_ws, target_path="src/main.py", dry_run=True
    )
    assert decision.allowed is True
    assert decision.decision_type == "ALLOW"


def test_live_mutation_requires_approval(active_ws: Workspace) -> None:
    pe = PolicyEngine(mutation_enabled=True)
    ctx = RequestContext(capability="workspace.patch", principal=Principal(id="agent"))
    decision = pe.evaluate_request(
        ctx,
        workspace=active_ws,
        target_path="src/main.py",
        dry_run=False,
        has_approval=False,
    )
    assert decision.allowed is False
    assert decision.decision_type == "REQUIRE_APPROVAL"
    assert decision.requires_approval() is True

    with pytest.raises(TacpApprovalRequiredError) as exc_info:
        pe.enforce(
            ctx,
            workspace=active_ws,
            target_path="src/main.py",
            dry_run=False,
            has_approval=False,
        )
    assert "requires approval" in str(exc_info.value).lower()


def test_live_mutation_allowed_with_approval(active_ws: Workspace) -> None:
    pe = PolicyEngine(mutation_enabled=True)
    ctx = RequestContext(capability="workspace.patch", principal=Principal(id="agent"))
    decision = pe.evaluate_request(
        ctx,
        workspace=active_ws,
        target_path="src/main.py",
        dry_run=False,
        has_approval=True,
    )
    assert decision.allowed is True
    assert decision.decision_type == "ALLOW"


def test_path_traversal_denied(active_ws: Workspace) -> None:
    pe = PolicyEngine(mutation_enabled=True)
    ctx = RequestContext(capability="workspace.patch", principal=Principal(id="agent"))
    for bad_path in ["../secret.txt", "foo/../../etc/passwd", "..\\escape"]:
        decision = pe.evaluate_request(
            ctx,
            workspace=active_ws,
            target_path=bad_path,
            dry_run=True,
        )
        assert decision.allowed is False
        assert decision.decision_type == "DENY"


def test_protected_files_denied(active_ws: Workspace) -> None:
    pe = PolicyEngine(mutation_enabled=True)
    ctx = RequestContext(capability="workspace.patch", principal=Principal(id="agent"))
    for protected in [
        ".git/config",
        "sub/.git/HEAD",
        ".tacp/tacp.db",
        ".env",
        ".env.local",
        "keys/id_rsa",
        "keys/id_ed25519",
    ]:
        decision = pe.evaluate_request(
            ctx,
            workspace=active_ws,
            target_path=protected,
            dry_run=True,
        )
        assert decision.allowed is False
        assert decision.decision_type == "DENY"
        assert "protected resource" in decision.reason


def test_suspended_workspace_denied(suspended_ws: Workspace) -> None:
    pe = PolicyEngine(mutation_enabled=True)
    ctx = RequestContext(capability="workspace.patch", principal=Principal(id="agent"))
    decision = pe.evaluate_request(
        ctx,
        workspace=suspended_ws,
        target_path="src/main.py",
        dry_run=True,
    )
    assert decision.allowed is False
    assert decision.decision_type == "DENY"
    assert "not ACTIVE" in decision.reason


def test_missing_workspace_denied() -> None:
    pe = PolicyEngine(mutation_enabled=True)
    ctx = RequestContext(capability="workspace.patch", principal=Principal(id="agent"))
    decision = pe.evaluate_request(
        ctx,
        workspace=None,
        target_path="src/main.py",
        dry_run=True,
    )
    assert decision.allowed is False
    assert decision.decision_type == "DENY"
    assert "requires an active workspace" in decision.reason


def test_batch_mutation_disabled_when_mutation_disabled(active_ws: Workspace) -> None:
    pe = PolicyEngine(mutation_enabled=False, batch_mutation_enabled=True)
    ctx = RequestContext(capability="workspace.patch_batch", principal=Principal(id="agent"))
    decision = pe.evaluate_request(ctx, workspace=active_ws)
    assert decision.allowed is False
    assert decision.decision_type == "DENY"
    assert "mutation is disabled" in decision.reason


def test_batch_mutation_disabled_when_batch_flag_false(active_ws: Workspace) -> None:
    pe = PolicyEngine(mutation_enabled=True, batch_mutation_enabled=False)
    ctx = RequestContext(capability="workspace.patch_batch", principal=Principal(id="agent"))
    decision = pe.evaluate_request(ctx, workspace=active_ws)
    assert decision.allowed is False
    assert decision.decision_type == "DENY"
    assert "batch mutation is disabled" in decision.reason


def test_batch_mutation_dry_run_allowed_when_both_enabled(active_ws: Workspace) -> None:
    pe = PolicyEngine(mutation_enabled=True, batch_mutation_enabled=True)
    ctx = RequestContext(capability="workspace.patch_batch", principal=Principal(id="agent"))
    decision = pe.evaluate_request(
        ctx,
        workspace=active_ws,
        target_paths=["src/a.py", "src/b.py"],
        dry_run=True,
    )
    assert decision.allowed is True
    assert decision.decision_type == "ALLOW"


def test_batch_mutation_live_requires_approval(active_ws: Workspace) -> None:
    pe = PolicyEngine(mutation_enabled=True, batch_mutation_enabled=True)
    ctx = RequestContext(capability="workspace.patch_batch", principal=Principal(id="agent"))
    decision = pe.evaluate_request(
        ctx,
        workspace=active_ws,
        target_paths=["src/a.py", "src/b.py"],
        dry_run=False,
        has_approval=False,
    )
    assert decision.allowed is False
    assert decision.decision_type == "REQUIRE_APPROVAL"


def test_batch_mutation_live_allowed_with_approval(active_ws: Workspace) -> None:
    pe = PolicyEngine(mutation_enabled=True, batch_mutation_enabled=True)
    ctx = RequestContext(capability="workspace.patch_batch", principal=Principal(id="agent"))
    decision = pe.evaluate_request(
        ctx,
        workspace=active_ws,
        target_paths=["src/a.py", "src/b.py"],
        dry_run=False,
        has_approval=True,
    )
    assert decision.allowed is True
    assert decision.decision_type == "ALLOW"


def test_batch_target_paths_traversal_denied(active_ws: Workspace) -> None:
    pe = PolicyEngine(mutation_enabled=True, batch_mutation_enabled=True)
    ctx = RequestContext(capability="workspace.patch_batch", principal=Principal(id="agent"))
    decision = pe.evaluate_request(
        ctx,
        workspace=active_ws,
        target_paths=["src/clean.py", "src/../../etc/shadow"],
        dry_run=True,
    )
    assert decision.allowed is False
    assert decision.decision_type == "DENY"
    assert "traversal" in decision.reason.lower()


def test_batch_target_paths_protected_denied(active_ws: Workspace) -> None:
    pe = PolicyEngine(mutation_enabled=True, batch_mutation_enabled=True)
    ctx = RequestContext(capability="workspace.patch_batch", principal=Principal(id="agent"))
    decision = pe.evaluate_request(
        ctx,
        workspace=active_ws,
        target_paths=["src/clean.py", ".git/HEAD"],
        dry_run=True,
    )
    assert decision.allowed is False
    assert decision.decision_type == "DENY"
    assert "protected resource" in decision.reason
