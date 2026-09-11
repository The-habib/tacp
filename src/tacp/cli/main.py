"""CLI entry point for TACP."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from tacp.access.mcp.server import create_mcp_server
from tacp.core.capability_service import CapabilityService
from tacp.core.system_service import SystemService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import TacpApprovalRequiredError, TacpError
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database


def cmd_version(_args: argparse.Namespace) -> int:
    """Print version information."""
    info = SystemService.get_version()
    ver = info["tacp_version"]
    mcp_ver = info["mcp_protocol_version"]
    mode = info["mode"]
    print(f"TACP v{ver} (MCP {mcp_ver}, mode: {mode})")
    return 0


def cmd_capabilities(_args: argparse.Namespace) -> int:
    """List available capabilities."""
    caps = CapabilityService.list_raw()
    print(f"\n{'NAME':<20} {'DOMAIN':<15} {'DESCRIPTION'}")
    print("-" * 80)
    for cap in caps:
        print(f"{cap.name:<20} {cap.domain:<15} {cap.description}")
    print(f"\nTotal capabilities: {len(caps)} (all read-only)\n")
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    """Run environmental and health diagnostics."""
    print("========================================")
    print(" TACP 0.1 System Diagnostics (Doctor)   ")
    print("========================================")

    all_passed = True
    config = TacpConfig.load()

    # 1. Python runtime
    py_ver = sys.version.split()[0]
    if sys.version_info >= (3, 11):
        print(f"[PASS] Python Runtime: {py_ver} (>= 3.11)")
    else:
        print(f"[FAIL] Python Runtime: {py_ver} (requires >= 3.11)")
        all_passed = False

    # 2. Operating environment
    prefix = os.environ.get("PREFIX", "")
    is_termux = "com.termux" in prefix or Path("/data/data/com.termux").exists()
    if is_termux:
        print(f"[PASS] Termux Environment: Active (PREFIX: {prefix})")
    else:
        print(f"[INFO] Host Environment: Linux/POSIX (PREFIX: {prefix or 'N/A'})")

    # 3. Database connectivity and WAL mode
    try:
        db = Database(config.db_path)
        conn = db.connect()
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0]
        if journal_mode.upper() == "WAL":
            print(f"[PASS] SQLite Database: {config.db_path} (WAL mode active)")
        else:
            print(f"[WARN] SQLite Database: {config.db_path} (journal_mode: {journal_mode})")
    except Exception as exc:
        print(f"[FAIL] SQLite Database: Connection error: {exc}")
        all_passed = False

    # 4. Workspaces check
    try:
        ws_service = WorkspaceService(db)
        workspaces = ws_service.list_workspaces()
        print(f"[PASS] Workspaces: {len(workspaces)} registered")
    except Exception as exc:
        print(f"[FAIL] Workspaces: Failed to query: {exc}")
        all_passed = False

    # 5. Security read-only baseline
    if config.read_only:
        print("[PASS] Security Baseline: Read-only enforcement ACTIVE")
    else:
        print("[FAIL] Security Baseline: Read-only enforcement INACTIVE")
        all_passed = False

    # 6. Capabilities check
    caps = CapabilityService.list_raw()
    if len(caps) == 13:
        print(f"[PASS] Capabilities: All {len(caps)} read-only capabilities loaded")
    else:
        print(f"[WARN] Capabilities: {len(caps)} capabilities loaded (expected 13)")

    print("----------------------------------------")
    if all_passed:
        print("[OK] All critical doctor checks passed. System is ready.")
        return 0
    else:
        print("[ERROR] One or more doctor checks failed.")
        return 1


def cmd_status(_args: argparse.Namespace) -> int:
    """Show runtime status."""
    config = TacpConfig.load()
    db = Database(config.db_path)
    db.connect()

    sys_service = SystemService(db)
    health = sys_service.get_health()
    info = sys_service.inspect_system()
    ws_service = WorkspaceService(db)
    workspaces = ws_service.list_workspaces()

    print("========================================")
    print(" TACP 0.1 Runtime Status                ")
    print("========================================")
    print(f"Overall Health   : {health['status']}")
    print(f"Database Healthy : {health['database_healthy']}")
    print(f"Database Path    : {config.db_path}")
    print(f"Read-Only Mode   : {config.read_only}")
    print(f"Active Workspaces: {len(workspaces)}")
    for ws in workspaces:
        print(f"  - [{ws['id']}] {ws['name']} -> {ws['root_path']}")
    print(f"System Arch      : {info.get('arch')}")
    print(f"Kernel Release   : {info.get('kernel')}")
    mem = info.get("memory", {})
    if mem:
        print(f"Memory Total/Free: {mem.get('total_mb', 0)}MB / {mem.get('free_mb', 0)}MB")
    print("========================================")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Launch stdio MCP server loop."""
    config = TacpConfig.load()
    if getattr(args, "allow_mutation", False):
        object.__setattr__(config, "mutation_enabled", True)
        object.__setattr__(config, "read_only", False)
    if getattr(args, "allow_batch_mutation", False) and config.mutation_enabled:
        object.__setattr__(config, "batch_mutation_enabled", True)
    if getattr(args, "allow_execution", False):
        object.__setattr__(config, "execution_enabled", True)
        object.__setattr__(config, "read_only", False)

    server = create_mcp_server(config)

    # Optional initial workspace registration from CLI
    if getattr(args, "workspace", None):
        ws_path = Path(args.workspace).resolve()
        if ws_path.is_dir():
            db = Database(config.db_path)
            ws_service = WorkspaceService(db)
            name = getattr(args, "workspace_name", None) or ws_path.name
            try:
                ws_service.register_workspace(name=name, root_path=ws_path)
            except TacpError as exc:
                sys.stderr.write(f"Notice: Workspace not registered: {exc.message}\n")

    server.run_stdio()
    return 0


def cmd_patch(args: argparse.Namespace) -> int:
    """Manage single patch operations."""
    config = TacpConfig.load()
    db = Database(config.db_path)
    db.connect()
    from tacp.control.approval import ApprovalEngine
    from tacp.control.policy import PolicyEngine
    from tacp.core.audit_service import AuditService
    from tacp.core.lock_service import LockService
    from tacp.core.patch_service import PatchService
    from tacp.core.workspace_service import WorkspaceService
    from tacp.providers.filesystem import FilesystemProvider

    ws_service = WorkspaceService(db)
    policy_engine = PolicyEngine(
        read_only_enforced=config.read_only,
        mutation_enabled=config.mutation_enabled,
        batch_mutation_enabled=config.batch_mutation_enabled,
    )
    fs_provider = FilesystemProvider(limits=config.limits)
    audit_service = AuditService(db)
    lock_service = LockService(db)
    approval_engine = ApprovalEngine(db)
    patch_service = PatchService(
        db=db,
        workspace_service=ws_service,
        policy_engine=policy_engine,
        fs_provider=fs_provider,
        audit_service=audit_service,
        lock_service=lock_service,
        approval_engine=approval_engine,
        config=config,
    )

    subcommand = getattr(args, "patch_action", None)
    if subcommand == "list" or subcommand is None:
        ws_id = getattr(args, "workspace", None)
        patches = patch_service.list_patches(workspace_id=ws_id)
        if not patches:
            print("No patch records found.")
            return 0
        print(f"\n{'PATCH ID':<16} {'WORKSPACE':<15} {'STATUS':<12} {'TARGET PATH'}")
        print("-" * 65)
        for p in patches:
            print(f"{p['id']:<16} {p['workspace_id']:<15} {p['status']:<12} {p['target_path']}")
        print()
        return 0

    elif subcommand == "show":
        patch_id = getattr(args, "patch_id", None)
        if not patch_id:
            print("Error: patch_id required.")
            return 1
        data = patch_service.get_patch(patch_id)
        if not data:
            print(f"Error: Patch '{patch_id}' not found.")
            return 1
        print(json.dumps(data, indent=2))
        return 0

    elif subcommand == "rollback":
        patch_id = getattr(args, "patch_id", None)
        if not patch_id:
            print("Error: patch_id required.")
            return 1
        try:
            res = patch_service.rollback_patch(patch_id, principal_id="cli-user")
            print(f"Successfully rolled back patch '{patch_id}': {res.message}")
            return 0
        except Exception as exc:
            print(f"Error rolling back patch '{patch_id}': {exc}")
            return 1

    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    """Manage batch patch operations."""
    config = TacpConfig.load()
    db = Database(config.db_path)
    db.connect()
    from tacp.control.approval import ApprovalEngine
    from tacp.control.policy import PolicyEngine
    from tacp.core.audit_service import AuditService
    from tacp.core.lock_service import LockService
    from tacp.core.patch_service import PatchService
    from tacp.core.workspace_service import WorkspaceService
    from tacp.providers.filesystem import FilesystemProvider

    ws_service = WorkspaceService(db)
    policy_engine = PolicyEngine(
        read_only_enforced=config.read_only,
        mutation_enabled=config.mutation_enabled,
        batch_mutation_enabled=config.batch_mutation_enabled,
    )
    fs_provider = FilesystemProvider(limits=config.limits)
    audit_service = AuditService(db)
    lock_service = LockService(db)
    approval_engine = ApprovalEngine(db)
    patch_service = PatchService(
        db=db,
        workspace_service=ws_service,
        policy_engine=policy_engine,
        fs_provider=fs_provider,
        audit_service=audit_service,
        lock_service=lock_service,
        approval_engine=approval_engine,
        config=config,
    )

    subcommand = getattr(args, "batch_action", None)
    if subcommand == "list" or subcommand is None:
        ws_id = getattr(args, "workspace", None)
        batches = patch_service.list_batches(workspace_id=ws_id)
        if not batches:
            print("No batch patch records found.")
            return 0
        print(f"\n{'BATCH ID':<20} {'WORKSPACE':<15} {'FILES':<8} {'STATUS':<12} {'APPLIED AT'}")
        print("-" * 75)
        for b in batches:
            print(
                f"{b['id']:<20} {b['workspace_id']:<15} {b['patch_count']:<8} "
                f"{b['status']:<12} {b['applied_at'][:19]}"
            )
        print()
        return 0

    elif subcommand == "show":
        batch_id = getattr(args, "batch_id", None)
        if not batch_id:
            print("Error: batch_id required.")
            return 1
        data = patch_service.get_batch(batch_id)
        if not data:
            print(f"Error: Batch '{batch_id}' not found.")
            return 1
        print(json.dumps(data, indent=2))
        return 0

    elif subcommand == "rollback":
        batch_id = getattr(args, "batch_id", None)
        if not batch_id:
            print("Error: batch_id required.")
            return 1
        try:
            res = patch_service.rollback_batch(batch_id, principal_id="cli-user")
            print(f"Successfully rolled back batch '{batch_id}': {res.message}")
            for r in res.results:
                print(f"  - {r.subpath}: restored {r.after_checksum[:12]}...")
            return 0
        except Exception as exc:
            print(f"Error rolling back batch '{batch_id}': {exc}")
            return 1

    return 0


def cmd_execution(args: argparse.Namespace) -> int:
    """Manage governed command executions."""
    config = TacpConfig.load()
    if getattr(args, "allow_execution", False):
        object.__setattr__(config, "execution_enabled", True)
        object.__setattr__(config, "read_only", False)

    db = Database(config.db_path)
    db.connect()
    from tacp.control.approval import ApprovalEngine
    from tacp.control.identity import Principal
    from tacp.control.policy import PolicyEngine
    from tacp.core.audit_service import AuditService
    from tacp.core.execution_resolver import ExecutionResolver
    from tacp.core.execution_service import ExecutionService
    from tacp.core.workspace_service import WorkspaceService
    from tacp.providers.process_executor import ProcessExecutor

    ws_service = WorkspaceService(db)
    policy_engine = PolicyEngine(
        read_only_enforced=config.read_only,
        mutation_enabled=config.mutation_enabled,
        batch_mutation_enabled=config.batch_mutation_enabled,
        execution_enabled=config.execution_enabled,
    )
    audit_service = AuditService(db)
    approval_engine = ApprovalEngine(db)
    resolver = ExecutionResolver(limits=config.limits)
    executor = ProcessExecutor()
    execution_service = ExecutionService(
        db=db,
        config=config,
        policy_engine=policy_engine,
        approval_engine=approval_engine,
        audit_service=audit_service,
        workspace_service=ws_service,
        resolver=resolver,
        executor=executor,
    )

    subcommand = getattr(args, "exec_action", None)
    if subcommand == "list" or subcommand is None:
        ws_id = getattr(args, "workspace", None)
        limit = getattr(args, "limit", 20) or 20
        records = execution_service.list_executions(workspace_id=ws_id, limit=limit)
        if not records:
            print("No execution records found.")
            return 0
        hdr = (
            f"\n{'EXECUTION ID':<20} {'WORKSPACE':<15} {'STATUS':<12} "
            f"{'EXEC':<10} {'CODE':<6} {'DURATION'}"
        )
        print(hdr)
        print("-" * 75)
        for r in records:
            dur = f"{r.get('duration_ms', 0):.1f}ms" if r.get("duration_ms") is not None else "-"
            code = str(r.get("exit_code")) if r.get("exit_code") is not None else "-"
            eid = r.get("execution_id") or r.get("id", "")
            row_str = (
                f"{eid:<20} {r['workspace_id']:<15} {r['status']:<12} "
                f"{r['executable']:<10} {code:<6} {dur}"
            )
            print(row_str)
        print()
        return 0

    elif subcommand == "inspect":
        exec_id = getattr(args, "execution_id", None)
        if not exec_id:
            print("Error: execution_id required.")
            return 1
        rec = execution_service.inspect_execution(exec_id)
        if not rec:
            print(f"Error: Execution record '{exec_id}' not found.")
            return 1
        print(json.dumps(rec, indent=2))
        return 0

    elif subcommand == "cancel":
        exec_id = getattr(args, "execution_id", None)
        if not exec_id:
            print("Error: execution_id required.")
            return 1
        try:
            res = execution_service.cancel_execution(
                exec_id, principal=Principal.local_agent("cli-operator")
            )
            st = res.get("status", "CANCELLED")
            print(f"Successfully cancelled execution '{exec_id}': {st}")
            return 0
        except Exception as exc:
            print(f"Error cancelling execution '{exec_id}': {exc}")
            return 1

    elif subcommand == "emergency-stop":
        operator_principal = Principal.human_operator("cli_operator")
        try:
            cancelled = execution_service.emergency_stop(principal=operator_principal)
            print(f"Emergency stop completed: {cancelled} active executions terminated.")
            return 0
        except Exception as exc:
            print(f"Failed to execute emergency stop: {exc}")
            return 1

    elif subcommand == "request":
        contract_file = getattr(args, "contract_file", None)
        if contract_file:
            path = Path(contract_file)
            if not path.is_file():
                print(f"Error: contract file not found: {contract_file}")
                return 1
            with open(path, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            ws_id = cdata.get("workspace_id")
            exe = cdata.get("executable")
            cmd_args = cdata.get("argv", [])
            cwd = cdata.get("cwd", ".")
            timeout = cdata.get("timeout_seconds")
            dry_run = cdata.get("dry_run", False)
        else:
            ws_id = getattr(args, "workspace", None)
            if not ws_id:
                print("Error: --workspace required for command request.")
                return 1
            exe = getattr(args, "executable", None)
            if not exe:
                print("Error: --executable required for command request.")
                return 1
            cmd_args = getattr(args, "args", []) or []
            dry_run = getattr(args, "dry_run", False)
            timeout = getattr(args, "timeout", None)
            cwd = getattr(args, "cwd", ".")

        approval_token = getattr(args, "approval_token", None)
        principal_id = getattr(args, "principal", "cli-user")
        try:
            try:
                result = execution_service.execute_command(
                    workspace_id=ws_id,
                    executable=exe,
                    argv=cmd_args,
                    cwd=cwd,
                    timeout_seconds=int(timeout) if timeout else None,
                    dry_run=dry_run,
                    approval_token=approval_token,
                    principal_id=principal_id,
                )
            except TacpApprovalRequiredError as appr_err:
                if getattr(args, "auto_approve", False):
                    tok = appr_err.details.get("token")
                    if tok:
                        approval_engine.approve(tok, approved_by="cli-operator")
                        result = execution_service.execute_command(
                            workspace_id=ws_id,
                            executable=exe,
                            argv=cmd_args,
                            cwd=cwd,
                            timeout_seconds=int(timeout) if timeout else None,
                            dry_run=dry_run,
                            approval_token=tok,
                            principal_id=principal_id,
                        )
                    else:
                        raise
                else:
                    raise

            if getattr(args, "json", False):
                print(json.dumps(result.to_dict(), indent=2))
            else:
                print(f"Execution ID   : {result.execution_id}")
                st = result.status.value if hasattr(result.status, "value") else str(result.status)
                print(f"Status         : {st}")
                print(f"Exit Code      : {result.exit_code}")
                dur = f"{result.duration_ms:.1f}ms" if result.duration_ms is not None else "-"
                print(f"Duration       : {dur}")
                if result.stdout:
                    print("\n--- STDOUT ---")
                    print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
                if result.stderr:
                    print("\n--- STDERR ---")
                    print(result.stderr, end="" if result.stderr.endswith("\n") else "\n")
            if result.status == "DRY_RUN":
                return 0
            return 0 if result.exit_code == 0 else (result.exit_code or 1)
        except Exception as exc:
            print(f"Execution Error: {exc}")
            return 1

    return 0


def cmd_workspace(args: argparse.Namespace) -> int:
    """Manage workspaces."""
    config = TacpConfig.load()
    db = Database(config.db_path)
    db.connect()
    ws_service = WorkspaceService(db)

    subcommand = getattr(args, "ws_action", None)
    if subcommand == "list" or subcommand is None:
        workspaces = ws_service.list_workspaces()
        if not workspaces:
            print("No workspaces registered.")
            return 0
        print(f"\n{'ID':<10} {'NAME':<15} {'STATUS':<10} {'ROOT PATH'}")
        print("-" * 60)
        for ws in workspaces:
            print(f"{ws['id']:<10} {ws['name']:<15} {ws['status']:<10} {ws['root_path']}")
        print()
        return 0

    elif subcommand == "add":
        path_str = getattr(args, "path", None)
        if not path_str:
            print("Error: Path required to add workspace.")
            return 1
        ws_path = Path(path_str).resolve()
        name = getattr(args, "name", None) or ws_path.name
        try:
            new_ws = ws_service.register_workspace(name=name, root_path=ws_path)
            print(f"Registered workspace '{new_ws.name}' [{new_ws.id}] at {new_ws.root_path}")
            return 0
        except TacpError as exc:
            print(f"Error: {exc.message}")
            return 1

    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """View recent audit events."""
    config = TacpConfig.load()
    db = Database(config.db_path)
    db.connect()
    from tacp.core.audit_service import AuditService

    audit_service = AuditService(db)
    limit = getattr(args, "limit", 20) or 20
    events = audit_service.get_recent_events(limit=limit)

    if getattr(args, "json", False):
        print(json.dumps(events, indent=2))
        return 0

    if not events:
        print("No audit events recorded.")
        return 0

    print(f"\n{'TIMESTAMP':<25} {'CAPABILITY':<18} {'DECISION':<10} {'RESULT'}")
    print("-" * 75)
    for ev in events:
        print(
            f"{ev.get('timestamp', '')[:23]:<25} "
            f"{ev.get('capability', ''):<18} "
            f"{ev.get('policy_decision', ''):<10} "
            f"{ev.get('result', '')}"
        )
    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="tacp",
        description="Termux AI Control Plane (TACP)",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # version
    subparsers.add_parser("version", help="Show version information")

    # capabilities
    subparsers.add_parser("capabilities", help="List registered capabilities")

    # doctor
    subparsers.add_parser("doctor", help="Run environmental and health diagnostics")

    # status
    subparsers.add_parser("status", help="Show runtime system status")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start the stdio MCP server loop")
    serve_parser.add_argument("--workspace", type=str, help="Initial workspace directory")
    serve_parser.add_argument("--workspace-name", type=str, help="Initial workspace name")
    serve_parser.add_argument(
        "--allow-mutation",
        action="store_true",
        help="Enable single-file workspace mutation",
    )
    serve_parser.add_argument(
        "--allow-batch-mutation",
        action="store_true",
        help="Enable multi-file batch workspace mutation",
    )
    serve_parser.add_argument(
        "--allow-execution",
        action="store_true",
        help="Enable controlled command execution",
    )

    # execution
    exec_parser = subparsers.add_parser("execution", help="Manage governed command execution")
    exec_sub = exec_parser.add_subparsers(dest="exec_action")

    # execution list
    exec_list = exec_sub.add_parser("list", help="List execution records")
    exec_list.add_argument("--workspace", help="Filter by workspace ID")
    exec_list.add_argument("--limit", type=int, default=20, help="Number of records to show")

    # execution inspect
    exec_inspect = exec_sub.add_parser("inspect", help="Inspect execution record")
    exec_inspect.add_argument("execution_id", help="Execution record ID")

    # execution cancel
    exec_cancel = exec_sub.add_parser("cancel", help="Cancel execution")
    exec_cancel.add_argument("execution_id", help="Execution record ID")

    # execution emergency-stop
    exec_sub.add_parser("emergency-stop", help="Emergency stop all active executions")

    # execution request
    exec_req = exec_sub.add_parser("request", help="Request governed command execution")
    exec_req.add_argument("--workspace", help="Workspace ID")
    exec_req.add_argument("--executable", help="Executable name (e.g. printf, echo, true)")
    exec_req.add_argument("--args", nargs="*", default=[], help="Command arguments")
    exec_req.add_argument("--cwd", default=".", help="Working directory relative to workspace")
    exec_req.add_argument("--dry-run", action="store_true", help="Run in dry-run mode")
    exec_req.add_argument(
        "--timeout", type=float, default=30.0, help="Execution timeout in seconds"
    )
    exec_req.add_argument("--stdin", help="Input string for stdin")
    exec_req.add_argument("--approval-token", help="Approval token if required")
    exec_req.add_argument("--contract-file", help="Path to JSON file containing execution contract")
    exec_req.add_argument(
        "--allow-execution", action="store_true", help="Enable execution capability"
    )
    exec_req.add_argument(
        "--auto-approve", action="store_true", help="Automatically approve execution ticket"
    )
    exec_req.add_argument("--json", action="store_true", help="Output in JSON format")
    exec_req.add_argument("--principal", default="cli-user", help="Principal identity")

    # patch
    patch_parser = subparsers.add_parser("patch", help="Manage single patches")
    patch_sub = patch_parser.add_subparsers(dest="patch_action")
    patch_list = patch_sub.add_parser("list", help="List patch records")
    patch_list.add_argument("--workspace", help="Filter by workspace ID")
    patch_show = patch_sub.add_parser("show", help="Show patch details")
    patch_show.add_argument("patch_id", help="Patch record ID")
    patch_rb = patch_sub.add_parser("rollback", help="Roll back a patch")
    patch_rb.add_argument("patch_id", help="Patch record ID")

    # batch
    batch_parser = subparsers.add_parser("batch", help="Manage multi-file patch batches")
    batch_sub = batch_parser.add_subparsers(dest="batch_action")
    batch_list = batch_sub.add_parser("list", help="List batch records")
    batch_list.add_argument("--workspace", help="Filter by workspace ID")
    batch_show = batch_sub.add_parser("show", help="Show batch details")
    batch_show.add_argument("batch_id", help="Batch record ID")
    batch_rb = batch_sub.add_parser("rollback", help="Roll back a patch batch")
    batch_rb.add_argument("batch_id", help="Batch record ID")

    # workspace
    ws_parser = subparsers.add_parser("workspace", help="Manage workspaces")
    ws_sub = ws_parser.add_subparsers(dest="ws_action")
    ws_sub.add_parser("list", help="List registered workspaces")
    add_parser = ws_sub.add_parser("add", help="Add a workspace directory")
    add_parser.add_argument("path", help="Directory path for workspace")
    add_parser.add_argument("--name", help="Workspace display name")

    # audit
    audit_parser = subparsers.add_parser("audit", help="View recent audit logs")
    audit_parser.add_argument("--limit", type=int, default=20, help="Number of records to show")
    audit_parser.add_argument("--json", action="store_true", help="Output in JSON format")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "version": cmd_version,
        "capabilities": cmd_capabilities,
        "doctor": cmd_doctor,
        "status": cmd_status,
        "serve": cmd_serve,
        "patch": cmd_patch,
        "batch": cmd_batch,
        "workspace": cmd_workspace,
        "audit": cmd_audit,
        "execution": cmd_execution,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
