"""Unit tests for Phase 6.5: Remote Governance, REMOTE_READ_ONLY Profile & REMOTE_AI Identity."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

from tacp.access.mcp.server import create_mcp_server
from tacp.access.mcp.tools import McpToolRegistry
from tacp.control.identity import (
    Authority,
    CredentialSource,
    Principal,
    PrincipalType,
    RequestContext,
    TrustTier,
)
from tacp.control.lease import LeaseEngine
from tacp.control.policy import PolicyEngine
from tacp.infrastructure.config import TacpConfig


@pytest.fixture
def remote_env() -> Generator[Dict[str, Any], None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        db_path = root / "tacp_remote_test.db"
        ws_root = root / "workspace"
        ws_root.mkdir()

        cfg = TacpConfig(
            data_dir=root,
            db_path=db_path,
            read_only=True,
            mutation_enabled=False,
            batch_mutation_enabled=False,
            execution_enabled=False,
            network_enabled=False,
            trust_profile="REMOTE_READ_ONLY",
            remote_enabled=True,
            remote_read_only=True,
            remote_mutation_enabled=False,
            remote_execution_enabled=False,
        )
        server = create_mcp_server(cfg)
        ws_service = server.tool_registry.workspace_service
        ws = ws_service.register_workspace("test-remote-ws", ws_root)
        patch_svc = server.tool_registry.patch_service

        yield {
            "server": server,
            "db": patch_svc.db if patch_svc else None,
            "ws": ws,
            "ws_root": ws_root,
            "policy": server.tool_registry.policy_engine,
            "lease_engine": server.tool_registry.lease_engine,
            "tool_registry": server.tool_registry,
            "cap_service": server.tool_registry.capability_service,
        }


class TestRemoteIdentity:
    def test_remote_ai_principal_creation(self) -> None:
        p = Principal.remote_ai("chatgpt-session-1")
        assert p.id == "chatgpt-session-1"
        assert p.principal_type == PrincipalType.REMOTE_AI
        assert p.credential_source == CredentialSource.TUNNEL
        assert p.trust_tier == TrustTier.RESTRICTED
        assert p.authenticated is True
        assert p.has_authority(Authority.READ_WORKSPACE) is True
        assert p.has_authority(Authority.MUTATE_WORKSPACE) is False
        assert p.has_authority(Authority.EXECUTE_COMMAND) is False
        assert p.has_authority(Authority.APPROVE_ACTION) is False
        assert p.is_elevated() is False

    def test_remote_ai_cannot_inherit_human_authority(self) -> None:
        remote_p = Principal.remote_ai("chatgpt")
        human_p = Principal.human_operator("operator")

        assert remote_p.is_elevated() is False
        assert human_p.is_elevated() is True
        assert human_p.has_authority(Authority.MUTATE_WORKSPACE) is True
        assert remote_p.has_authority(Authority.MUTATE_WORKSPACE) is False


class TestRemoteReadOnlyProfilePolicy:
    def test_r0_observation_allowed_in_remote_read_only(self, remote_env: Dict[str, Any]) -> None:
        policy: PolicyEngine = remote_env["policy"]
        ws = remote_env["ws"]
        principal = Principal.remote_ai()

        r0_caps = [
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

        for cap in r0_caps:
            ctx = RequestContext(capability=cap, principal=principal)
            dec = policy.evaluate_request(ctx, workspace=ws, target_path="hello.txt")
            assert dec.allowed is True, f"Expected {cap} to be allowed under REMOTE_READ_ONLY"
            assert dec.decision_type == "ALLOW"

    def test_mutation_strictly_denied_in_remote_read_only(self, remote_env: Dict[str, Any]) -> None:
        policy: PolicyEngine = remote_env["policy"]
        ws = remote_env["ws"]
        principal = Principal.remote_ai()

        mutating_caps = [
            "workspace.patch",
            "workspace.patch_batch",
            "workspace.rollback",
            "workspace.batch_rollback",
        ]

        for cap in mutating_caps:
            ctx = RequestContext(capability=cap, principal=principal)
            dec = policy.evaluate_request(ctx, workspace=ws, target_path="code.py")
            assert dec.allowed is False
            assert dec.decision_type == "DENY"
            assert (
                "REMOTE_READ_ONLY" in dec.reason
                or "read-only mode" in dec.reason
                or "prohibited" in dec.reason
            )

    def test_execution_strictly_denied_in_remote_read_only(
        self, remote_env: Dict[str, Any]
    ) -> None:
        policy: PolicyEngine = remote_env["policy"]
        ws = remote_env["ws"]
        principal = Principal.remote_ai()

        exec_caps = [
            "execution.request",
            "execution.inspect",
            "execution.list",
            "execution.cancel",
        ]

        for cap in exec_caps:
            ctx = RequestContext(capability=cap, principal=principal)
            dec = policy.evaluate_request(ctx, workspace=ws)
            assert dec.allowed is False
            assert dec.decision_type == "DENY"

    def test_audit_verify_integrity_denied_to_remote_ai(self, remote_env: Dict[str, Any]) -> None:
        policy: PolicyEngine = remote_env["policy"]
        ws = remote_env["ws"]
        principal = Principal.remote_ai()

        ctx = RequestContext(capability="audit.verify_integrity", principal=principal)
        dec = policy.evaluate_request(ctx, workspace=ws)
        assert dec.allowed is False
        assert dec.decision_type == "DENY"

    def test_remote_disabled_blocks_all_remote_calls(self, remote_env: Dict[str, Any]) -> None:
        le: LeaseEngine = remote_env["lease_engine"]
        policy = PolicyEngine(
            read_only_enforced=True,
            trust_profile="REMOTE_READ_ONLY",
            lease_engine=le,
            remote_enabled=False,  # Explicitly disabled
        )
        ws = remote_env["ws"]
        principal = Principal.remote_ai()

        ctx = RequestContext(capability="system.inspect", principal=principal)
        dec = policy.evaluate_request(ctx, workspace=ws)
        assert dec.allowed is False
        assert dec.decision_type == "DENY"
        assert "Remote access is disabled" in dec.reason

    def test_capability_leases_rejected_in_remote_read_only(
        self, remote_env: Dict[str, Any]
    ) -> None:
        policy: PolicyEngine = remote_env["policy"]
        le: LeaseEngine = remote_env["lease_engine"]
        ws = remote_env["ws"]
        principal = Principal.remote_ai()

        # Create lease
        lease = le.create_lease(principal.id, ws.id, ["workspace.patch"])
        ctx = RequestContext(capability="workspace.patch", principal=principal)
        dec = policy.evaluate_request(
            ctx, workspace=ws, target_path="a.py", lease_id=lease.lease_id
        )
        assert dec.allowed is False
        assert dec.decision_type == "DENY"


class TestToolExposureAudit:
    def test_remote_read_only_exposes_only_r0_tools(self, remote_env: Dict[str, Any]) -> None:
        tool_reg: McpToolRegistry = remote_env["tool_registry"]
        tools = tool_reg.list_tools()
        tool_names = {t["name"] for t in tools}

        assert len(tools) == 13
        assert "system.inspect" in tool_names
        assert "system.health" in tool_names
        assert "system.version" in tool_names
        assert "capabilities.list" in tool_names
        assert "workspace.list" in tool_names
        assert "workspace.inspect" in tool_names
        assert "fs.list" in tool_names
        assert "fs.stat" in tool_names
        assert "fs.read" in tool_names
        assert "fs.search" in tool_names
        assert "process.list" in tool_names
        assert "process.inspect" in tool_names
        assert "audit.recent" in tool_names

        # Prohibited in REMOTE_READ_ONLY:
        assert "workspace.patch" not in tool_names
        assert "workspace.patch_batch" not in tool_names
        assert "execution.request" not in tool_names
        assert "audit.verify_integrity" not in tool_names
