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
from tacp.domain.errors import TacpError
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
        description="Termux AI Control Plane (TACP) 0.1",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # version
    subparsers.add_parser("version", help="Show version information")

    # capabilities
    subparsers.add_parser("capabilities", help="List registered read-only capabilities")

    # doctor
    subparsers.add_parser("doctor", help="Run environmental and health diagnostics")

    # status
    subparsers.add_parser("status", help="Show runtime system status")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start the stdio MCP server loop")
    serve_parser.add_argument("--workspace", type=str, help="Initial workspace directory")
    serve_parser.add_argument("--workspace-name", type=str, help="Initial workspace name")

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
        "workspace": cmd_workspace,
        "audit": cmd_audit,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
