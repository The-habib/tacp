"""End-to-end integration tests for Phase 6 UX Scenarios A through F."""

from __future__ import annotations

import hashlib
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Generator

import pytest

from tacp.access.mcp.tools import McpToolRegistry
from tacp.control.approval import ApprovalEngine
from tacp.control.lease import LeaseEngine
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.capability_service import CapabilityService
from tacp.core.execution_service import ExecutionService
from tacp.core.filesystem_service import FilesystemService
from tacp.core.lock_service import LockService
from tacp.core.patch_service import PatchService
from tacp.core.process_service import ProcessService
from tacp.core.system_service import SystemService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import ErrorCode, TacpApprovalRequiredError, TacpSecurityError
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database
from tacp.providers.filesystem import FilesystemProvider
from tacp.providers.process import ProcessProvider


def make_diff(filename: str, old_text: str, new_text: str) -> str:
    return f"--- {filename}\n+++ {filename}\n@@ -1,1 +1,1 @@\n-{old_text}\n+{new_text}\n"


@pytest.fixture
def ux_environment() -> Generator[Dict[str, Any], None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        db_path = root / "tacp_ux.db"
        db = Database(db_path)
        cfg = TacpConfig(
            data_dir=root,
            db_path=db_path,
            mutation_enabled=True,
            batch_mutation_enabled=True,
            execution_enabled=True,
            trust_profile="BALANCED",
        )

        ws_service = WorkspaceService(db)
        ws_root = root / "project"
        ws_root.mkdir()
        ws = ws_service.register_workspace("project-alpha", ws_root)

        f1 = ws_root / "hello.py"
        f1.write_text("print('hello')\n")
        f2 = ws_root / "config.json"
        f2.write_text('{"version": "1.0.0"}\n')

        audit_svc = AuditService(db)
        lease_eng = LeaseEngine(db)
        appr_eng = ApprovalEngine(db)
        lock_svc = LockService(db)
        fs_prov = FilesystemProvider(limits=cfg.limits)
        fs_svc = FilesystemService(ws_service, fs_prov)
        proc_svc = ProcessService(ProcessProvider(limits=cfg.limits))
        sys_svc = SystemService(db)
        cap_svc = CapabilityService()

        policy_eng = PolicyEngine(
            read_only_enforced=False,
            mutation_enabled=True,
            batch_mutation_enabled=True,
            execution_enabled=True,
            trust_profile=cfg.trust_profile,
            lease_engine=lease_eng,
        )

        patch_svc = PatchService(
            db=db,
            workspace_service=ws_service,
            policy_engine=policy_eng,
            fs_provider=fs_prov,
            audit_service=audit_svc,
            lock_service=lock_svc,
            approval_engine=appr_eng,
            config=cfg,
            lease_engine=lease_eng,
        )

        exec_svc = ExecutionService(
            db=db,
            config=cfg,
            policy_engine=policy_eng,
            approval_engine=appr_eng,
            audit_service=audit_svc,
            workspace_service=ws_service,
            lease_engine=lease_eng,
        )

        tool_reg = McpToolRegistry(
            capability_service=cap_svc,
            policy_engine=policy_eng,
            audit_service=audit_svc,
            workspace_service=ws_service,
            filesystem_service=fs_svc,
            process_service=proc_svc,
            system_service=sys_svc,
            patch_service=patch_svc,
            execution_service=exec_svc,
            lease_engine=lease_eng,
        )

        yield {
            "root": root,
            "ws": ws,
            "ws_root": ws_root,
            "db": db,
            "cfg": cfg,
            "ws_service": ws_service,
            "audit_svc": audit_svc,
            "lease_eng": lease_eng,
            "appr_eng": appr_eng,
            "policy_eng": policy_eng,
            "patch_svc": patch_svc,
            "exec_svc": exec_svc,
            "tool_reg": tool_reg,
        }
        db.close()


def test_scenario_a_fast_path_read_operations(ux_environment: Dict[str, Any]) -> None:
    """Scenario A: Read operations (R0) execute swiftly with low latency and cache hits."""
    tool_reg: McpToolRegistry = ux_environment["tool_reg"]
    ws = ux_environment["ws"]

    res1 = tool_reg.execute_tool("fs.read", {"workspace_id": ws.id, "subpath": "hello.py"})
    assert "hello" in res1["content"]

    times = []
    for _ in range(10):
        t0 = time.perf_counter()
        res = tool_reg.execute_tool("fs.read", {"workspace_id": ws.id, "subpath": "hello.py"})
        times.append((time.perf_counter() - t0) * 1000)
        assert "hello" in res["content"]

    avg_ms = sum(times) / len(times)
    assert avg_ms < 15.0


def test_scenario_b_plan_first_dry_run_protocol(ux_environment: Dict[str, Any]) -> None:
    """Scenario B: Agent generates dry-run plan, human approves, execution succeeds."""
    tool_reg: McpToolRegistry = ux_environment["tool_reg"]
    appr_eng: ApprovalEngine = ux_environment["appr_eng"]
    ws = ux_environment["ws"]
    ws_root: Path = ux_environment["ws_root"]

    file_path = ws_root / "hello.py"
    base_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
    diff = make_diff("hello.py", "print('hello')", "print('hello world')")

    dry_res = tool_reg.execute_tool(
        "workspace.patch",
        {
            "workspace_id": ws.id,
            "subpath": "hello.py",
            "patch_content": diff,
            "base_checksum": base_hash,
            "dry_run": True,
        },
    )
    assert dry_res["status"] == "SIMULATED"
    assert file_path.read_text() == "print('hello')\n"

    with pytest.raises(TacpApprovalRequiredError) as exc:
        tool_reg.execute_tool(
            "workspace.patch",
            {
                "workspace_id": ws.id,
                "subpath": "hello.py",
                "patch_content": diff,
                "base_checksum": base_hash,
                "dry_run": False,
            },
        )
    err_msg = str(exc.value)
    token = err_msg.split("Ticket created: ")[1].split(" ")[0]

    appr_eng.approve(token, approved_by="human_dev")

    live_res = tool_reg.execute_tool(
        "workspace.patch",
        {
            "workspace_id": ws.id,
            "subpath": "hello.py",
            "patch_content": diff,
            "base_checksum": base_hash,
            "dry_run": False,
            "approval_token": token,
        },
    )
    assert live_res["status"] == "APPLIED"
    assert file_path.read_text() == "print('hello world')\n"


def test_scenario_c_bounded_capability_lease_multi_step(ux_environment: Dict[str, Any]) -> None:
    """Scenario C: Multi-step editing workflow under a lease without approval fatigue."""
    tool_reg: McpToolRegistry = ux_environment["tool_reg"]
    lease_eng: LeaseEngine = ux_environment["lease_eng"]
    ws = ux_environment["ws"]
    ws_root: Path = ux_environment["ws_root"]

    lease = lease_eng.create_lease(
        principal_id="mcp-client",
        workspace_id=ws.id,
        capabilities=["workspace.patch"],
        resources=["*"],
        budget=3,
        duration_seconds=1200,
    )

    f1 = ws_root / "hello.py"
    b1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    d1 = make_diff("hello.py", "print('hello')", "print('step 1')")
    r1 = tool_reg.execute_tool(
        "workspace.patch",
        {
            "workspace_id": ws.id,
            "subpath": "hello.py",
            "patch_content": d1,
            "base_checksum": b1,
            "lease_id": lease.lease_id,
        },
    )
    assert r1["status"] == "APPLIED"

    b2 = hashlib.sha256(f1.read_bytes()).hexdigest()
    d2 = make_diff("hello.py", "print('step 1')", "print('step 2')")
    r2 = tool_reg.execute_tool(
        "workspace.patch",
        {
            "workspace_id": ws.id,
            "subpath": "hello.py",
            "patch_content": d2,
            "base_checksum": b2,
            "lease_id": lease.lease_id,
        },
    )
    assert r2["status"] == "APPLIED"

    b3 = hashlib.sha256(f1.read_bytes()).hexdigest()
    d3 = make_diff("hello.py", "print('step 2')", "print('step 3')")
    r3 = tool_reg.execute_tool(
        "workspace.patch",
        {
            "workspace_id": ws.id,
            "subpath": "hello.py",
            "patch_content": d3,
            "base_checksum": b3,
            "lease_id": lease.lease_id,
        },
    )
    assert r3["status"] == "APPLIED"
    assert f1.read_text() == "print('step 3')\n"

    b4 = hashlib.sha256(f1.read_bytes()).hexdigest()
    d4 = make_diff("hello.py", "print('step 3')", "print('step 4')")
    with pytest.raises(TacpApprovalRequiredError):
        tool_reg.execute_tool(
            "workspace.patch",
            {
                "workspace_id": ws.id,
                "subpath": "hello.py",
                "patch_content": d4,
                "base_checksum": b4,
                "lease_id": lease.lease_id,
            },
        )


def test_scenario_d_developer_mode_low_friction(ux_environment: Dict[str, Any]) -> None:
    """Scenario D: In DEVELOPER profile, local workspace mutations proceed without tickets."""
    ws = ux_environment["ws"]
    ws_root: Path = ux_environment["ws_root"]
    from dataclasses import replace

    cfg = replace(ux_environment["cfg"], trust_profile="DEVELOPER")

    policy_dev = PolicyEngine(
        read_only_enforced=False,
        mutation_enabled=True,
        batch_mutation_enabled=True,
        execution_enabled=True,
        trust_profile="DEVELOPER",
    )
    patch_svc_dev = PatchService(
        db=ux_environment["db"],
        workspace_service=ux_environment["ws_service"],
        policy_engine=policy_dev,
        fs_provider=FilesystemProvider(),
        audit_service=ux_environment["audit_svc"],
        lock_service=LockService(ux_environment["db"]),
        approval_engine=ux_environment["appr_eng"],
        config=cfg,
    )

    f1 = ws_root / "hello.py"
    b1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    d1 = make_diff("hello.py", "print('hello')", "print('dev mode live edit')")

    res = patch_svc_dev.execute_patch(
        workspace_id=ws.id,
        subpath="hello.py",
        patch_content=d1,
        base_checksum=b1,
        dry_run=False,
    )
    assert res.status == "APPLIED"
    assert f1.read_text() == "print('dev mode live edit')\n"


def test_scenario_e_strict_mode_high_security(ux_environment: Dict[str, Any]) -> None:
    """Scenario E: In STRICT profile, every mutating/executing action requires approval."""
    ws = ux_environment["ws"]
    ws_root: Path = ux_environment["ws_root"]
    from dataclasses import replace

    cfg = replace(ux_environment["cfg"], trust_profile="STRICT")

    policy_strict = PolicyEngine(
        read_only_enforced=False,
        mutation_enabled=True,
        batch_mutation_enabled=True,
        execution_enabled=True,
        trust_profile="STRICT",
        lease_engine=ux_environment["lease_eng"],
    )
    patch_svc_strict = PatchService(
        db=ux_environment["db"],
        workspace_service=ux_environment["ws_service"],
        policy_engine=policy_strict,
        fs_provider=FilesystemProvider(),
        audit_service=ux_environment["audit_svc"],
        lock_service=LockService(ux_environment["db"]),
        approval_engine=ux_environment["appr_eng"],
        config=cfg,
        lease_engine=ux_environment["lease_eng"],
    )

    f1 = ws_root / "hello.py"
    b1 = hashlib.sha256(f1.read_bytes()).hexdigest()
    d1 = make_diff("hello.py", "print('hello')", "print('strict mode')")

    lease = ux_environment["lease_eng"].create_lease("agent-strict", ws.id, ["workspace.patch"])
    with pytest.raises(TacpApprovalRequiredError):
        patch_svc_strict.execute_patch(
            workspace_id=ws.id,
            subpath="hello.py",
            patch_content=d1,
            base_checksum=b1,
            lease_id=lease.lease_id,
            principal_id="agent-strict",
        )


def test_scenario_f_lockdown_emergency_mode(ux_environment: Dict[str, Any]) -> None:
    """Scenario F: LOCKDOWN profile immediately blocks all mutating and executing capabilities."""
    ws = ux_environment["ws"]
    tool_reg: McpToolRegistry = ux_environment["tool_reg"]
    policy_eng: PolicyEngine = ux_environment["policy_eng"]

    policy_eng.trust_profile = "LOCKDOWN"

    exposed_tools = [t["name"] for t in tool_reg.list_tools()]
    assert "workspace.patch" not in exposed_tools
    assert "workspace.patch_batch" not in exposed_tools
    assert "execution.request" not in exposed_tools
    assert "fs.read" in exposed_tools

    res = tool_reg.execute_tool("fs.read", {"workspace_id": ws.id, "subpath": "hello.py"})
    assert res is not None

    with pytest.raises(TacpSecurityError) as exc:
        tool_reg.execute_tool(
            "workspace.patch",
            {
                "workspace_id": ws.id,
                "subpath": "hello.py",
                "patch_content": "dummy",
                "base_checksum": "dummy",
            },
        )
    assert exc.value.code == ErrorCode.NOT_AUTHORIZED
