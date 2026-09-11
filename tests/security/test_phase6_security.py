"""Security and boundary test suite for TACP Phase 6."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

from tacp.access.mcp.tools import McpToolRegistry
from tacp.control.approval import ApprovalEngine
from tacp.control.identity import Principal, RequestContext
from tacp.control.lease import LeaseEngine
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.capability_service import CapabilityService
from tacp.core.filesystem_service import FilesystemService
from tacp.core.process_service import ProcessService
from tacp.core.system_service import SystemService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import ErrorCode, TacpSecurityError
from tacp.infrastructure.database import Database
from tacp.providers.filesystem import FilesystemProvider
from tacp.providers.process import ProcessProvider


@pytest.fixture
def sec_fixture() -> Generator[Dict[str, Any], None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        db_path = root / "tacp_sec.db"
        db = Database(db_path)
        ws_service = WorkspaceService(db)
        ws_root = root / "ws1"
        ws_root.mkdir()
        ws = ws_service.register_workspace("sec-ws", ws_root)

        ws2_root = root / "ws2"
        ws2_root.mkdir()
        ws2 = ws_service.register_workspace("sec-ws-other", ws2_root)

        audit_svc = AuditService(db)
        lease_engine = LeaseEngine(db)
        approval_engine = ApprovalEngine(db)
        cap_svc = CapabilityService()
        proc_svc = ProcessService(ProcessProvider())
        sys_svc = SystemService(db)
        fs_svc = FilesystemService(ws_service, FilesystemProvider())

        yield {
            "root": root,
            "db": db,
            "ws": ws,
            "ws2": ws2,
            "ws_service": ws_service,
            "audit_svc": audit_svc,
            "lease_engine": lease_engine,
            "approval_engine": approval_engine,
            "cap_svc": cap_svc,
            "proc_svc": proc_svc,
            "sys_svc": sys_svc,
            "fs_svc": fs_svc,
        }
        db.close()


class TestLeaseBoundarySecurity:
    def test_principal_mismatch_rejection(self, sec_fixture: Dict[str, Any]) -> None:
        le: LeaseEngine = sec_fixture["lease_engine"]
        ws = sec_fixture["ws"]
        lease = le.create_lease(
            principal_id="agent-legit",
            workspace_id=ws.id,
            capabilities=["workspace.patch"],
            budget=5,
        )

        with pytest.raises(TacpSecurityError) as exc:
            le.verify_and_consume(
                lease_id=lease.lease_id,
                principal_id="agent-impostor",
                capability="workspace.patch",
                workspace_id=ws.id,
                risk_level="R2",
            )
        assert exc.value.code == ErrorCode.NOT_AUTHORIZED
        assert "principal mismatch" in str(exc.value).lower()

    def test_workspace_mismatch_rejection(self, sec_fixture: Dict[str, Any]) -> None:
        le: LeaseEngine = sec_fixture["lease_engine"]
        ws = sec_fixture["ws"]
        ws2 = sec_fixture["ws2"]
        lease = le.create_lease(
            principal_id="agent-1",
            workspace_id=ws.id,
            capabilities=["workspace.patch"],
            budget=5,
        )

        with pytest.raises(TacpSecurityError) as exc:
            le.verify_and_consume(
                lease_id=lease.lease_id,
                principal_id="agent-1",
                capability="workspace.patch",
                workspace_id=ws2.id,
                risk_level="R2",
            )
        assert exc.value.code == ErrorCode.NOT_AUTHORIZED
        assert "workspace mismatch" in str(exc.value).lower()

    def test_capability_mismatch_rejection(self, sec_fixture: Dict[str, Any]) -> None:
        le: LeaseEngine = sec_fixture["lease_engine"]
        ws = sec_fixture["ws"]
        lease = le.create_lease(
            principal_id="agent-1",
            workspace_id=ws.id,
            capabilities=["workspace.patch"],
            budget=5,
        )

        with pytest.raises(TacpSecurityError) as exc:
            le.verify_and_consume(
                lease_id=lease.lease_id,
                principal_id="agent-1",
                capability="execution.request",
                workspace_id=ws.id,
                risk_level="R3",
            )
        assert exc.value.code == ErrorCode.NOT_AUTHORIZED

    def test_risk_ceiling_elevation_rejection(self, sec_fixture: Dict[str, Any]) -> None:
        le: LeaseEngine = sec_fixture["lease_engine"]
        ws = sec_fixture["ws"]
        lease = le.create_lease(
            principal_id="agent-1",
            workspace_id=ws.id,
            capabilities=["workspace.patch", "execution.request"],
            risk_ceiling="R2",
            budget=5,
        )

        with pytest.raises(TacpSecurityError) as exc:
            le.verify_and_consume(
                lease_id=lease.lease_id,
                principal_id="agent-1",
                capability="execution.request",
                workspace_id=ws.id,
                risk_level="R3",  # R3 exceeds R2 ceiling!
            )
        assert exc.value.code == ErrorCode.NOT_AUTHORIZED
        assert "exceeds lease risk ceiling" in str(exc.value).lower()

    def test_resource_path_escape_rejection(self, sec_fixture: Dict[str, Any]) -> None:
        le: LeaseEngine = sec_fixture["lease_engine"]
        ws = sec_fixture["ws"]
        lease = le.create_lease(
            principal_id="agent-1",
            workspace_id=ws.id,
            capabilities=["workspace.patch"],
            resources=["docs/*", "src/views/*"],
            budget=5,
        )

        # Allowed subpath
        assert (
            le.verify_and_consume(
                lease_id=lease.lease_id,
                principal_id="agent-1",
                capability="workspace.patch",
                workspace_id=ws.id,
                risk_level="R2",
                target_path="docs/guide.md",
            )
            is True
        )

        # Escaped subpath
        with pytest.raises(TacpSecurityError) as exc:
            le.verify_and_consume(
                lease_id=lease.lease_id,
                principal_id="agent-1",
                capability="workspace.patch",
                workspace_id=ws.id,
                risk_level="R2",
                target_path="src/auth/secrets.py",
            )
        assert exc.value.code == ErrorCode.NOT_AUTHORIZED
        assert "outside lease allowed resources" in str(exc.value).lower()

    def test_expired_lease_rejection(self, sec_fixture: Dict[str, Any]) -> None:
        le: LeaseEngine = sec_fixture["lease_engine"]
        ws = sec_fixture["ws"]
        db = sec_fixture["db"]
        lease = le.create_lease(
            principal_id="agent-1",
            workspace_id=ws.id,
            capabilities=["workspace.patch"],
            budget=5,
            duration_seconds=10,
        )

        # Force expires_at into the past in the database
        past = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        conn = db.connect()
        with conn:
            conn.execute(
                "UPDATE leases SET expires_at = ? WHERE lease_id = ?", (past, lease.lease_id)
            )

        with pytest.raises(TacpSecurityError) as exc:
            le.verify_and_consume(
                lease_id=lease.lease_id,
                principal_id="agent-1",
                capability="workspace.patch",
                workspace_id=ws.id,
                risk_level="R2",
            )
        assert exc.value.code == ErrorCode.APPROVAL_EXPIRED


class TestDynamicToolExposureSecurity:
    def test_lockdown_hides_all_mutating_and_executing_tools(
        self, sec_fixture: Dict[str, Any]
    ) -> None:
        policy = PolicyEngine(
            mutation_enabled=True,
            execution_enabled=True,
            trust_profile="LOCKDOWN",
        )
        reg = McpToolRegistry(
            capability_service=sec_fixture["cap_svc"],
            policy_engine=policy,
            audit_service=sec_fixture["audit_svc"],
            workspace_service=sec_fixture["ws_service"],
            filesystem_service=sec_fixture["fs_svc"],
            process_service=sec_fixture["proc_svc"],
            system_service=sec_fixture["sys_svc"],
        )

        tools = reg.list_tools()
        tool_names = {t["name"] for t in tools}

        assert "workspace.patch" not in tool_names
        assert "workspace.patch_batch" not in tool_names
        assert "execution.request" not in tool_names

        for name in tool_names:
            assert not name.startswith("workspace.patch")
            assert not name.startswith("execution.")

    def test_lockdown_enforcement_on_direct_tool_invocation(
        self, sec_fixture: Dict[str, Any]
    ) -> None:
        policy = PolicyEngine(
            mutation_enabled=True,
            execution_enabled=True,
            trust_profile="LOCKDOWN",
        )
        ws = sec_fixture["ws"]
        ctx = RequestContext(
            capability="workspace.patch", principal=Principal.local_agent("agent-1")
        )
        dec = policy.evaluate_request(ctx, workspace=ws, target_path="foo.txt")
        assert dec.allowed is False
        assert dec.decision_type == "DENY"
        assert "LOCKDOWN" in dec.reason


class TestNegativeInvariants:
    def test_developer_mode_never_sovereign_on_execution(self, sec_fixture: Dict[str, Any]) -> None:
        policy = PolicyEngine(
            execution_enabled=True,
            trust_profile="DEVELOPER",
        )
        ws = sec_fixture["ws"]
        ctx = RequestContext(
            capability="execution.request", principal=Principal.local_agent("agent-1")
        )
        dec = policy.evaluate_request(ctx, workspace=ws)
        assert dec.allowed is False
        assert dec.decision_type == "REQUIRE_APPROVAL"

    def test_strict_mode_rejects_lease_bypass(self, sec_fixture: Dict[str, Any]) -> None:
        le: LeaseEngine = sec_fixture["lease_engine"]
        ws = sec_fixture["ws"]
        lease = le.create_lease("ag", ws.id, ["workspace.patch"])
        policy = PolicyEngine(
            mutation_enabled=True,
            trust_profile="STRICT",
            lease_engine=le,
        )
        ctx = RequestContext(capability="workspace.patch", principal=Principal.local_agent("ag"))
        dec = policy.evaluate_request(ctx, workspace=ws, lease_id=lease.lease_id)
        assert dec.allowed is False
        assert dec.decision_type == "REQUIRE_APPROVAL"
