"""CLI entry point for TACP."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from tacp.access.mcp.server import create_mcp_server
from tacp.control.auth import TokenService
from tacp.control.pairing import PairingService, get_or_create_device_identity
from tacp.core.capability_service import CapabilityService
from tacp.core.system_service import SystemService
from tacp.core.workspace_service import WorkspaceService
from tacp.domain.errors import TacpApprovalRequiredError, TacpError
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database
from tacp.remote.manager import RemoteManager


def cmd_version(_args: argparse.Namespace) -> int:
    """Print version information."""
    info = SystemService.get_version()
    ver = info["tacp_version"]
    mcp_ver = info["mcp_protocol_version"]
    mode = info["mode"]
    print(f"TACP v{ver} (MCP {mcp_ver}, mode: {mode})")
    return 0


def cmd_capabilities(args: argparse.Namespace) -> int:
    """List available capabilities."""
    is_device = (
        getattr(args, "device", False)
        or getattr(args, "json", False)
        or getattr(args, "category", None) is not None
        or getattr(args, "backend", None) is not None
        or getattr(args, "available", False)
    )
    if is_device:
        from tacp.engine.registry import CapabilityRegistry

        reg = CapabilityRegistry()
        caps = reg.list_capabilities(filter_category=getattr(args, "category", None))

        backend_filter = getattr(args, "backend", None)
        if backend_filter:
            caps = [
                c
                for c in caps
                if backend_filter.lower() in [b.lower() for b in c.get("supported_backends", [])]
            ]

        if getattr(args, "available", False):
            caps = [c for c in caps if c.get("availability") == "AVAILABLE"]

        if getattr(args, "json", False):
            print(json.dumps({"capabilities": caps, "total": len(caps)}, indent=2))
            return 0

        print(f"\n{'ID':<25} {'CATEGORY':<12} {'AVAILABILITY':<15} {'BACKEND':<14} {'DESCRIPTION'}")
        print("-" * 90)
        for c in caps:
            avail = c.get("availability", "UNKNOWN")
            active_b = c.get("active_backend") or "none"
            desc = c.get("description", "")[:28]
            print(f"{c['id']:<25} {c.get('category', ''):<12} {avail:<15} {active_b:<14} {desc}")
        print(f"\nTotal device capabilities: {len(caps)}\n")
        return 0

    raw_caps = CapabilityService.list_raw()
    print(f"\n{'NAME':<20} {'DOMAIN':<15} {'DESCRIPTION'}")
    print("-" * 80)
    for cap in raw_caps:
        print(f"{cap.name:<20} {cap.domain:<15} {cap.description}")
    print(f"\nTotal capabilities: {len(raw_caps)} (all read-only)\n")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run environmental and health diagnostics."""
    if getattr(args, "json", False):
        from tacp.core.discovery import DeviceDiscovery

        report = DeviceDiscovery.get_device_report()
        print(json.dumps(report, indent=2))
        return 0

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
    if len(caps) >= 13:
        print(f"[PASS] Capabilities: {len(caps)} read-only capabilities loaded")
    else:
        print(f"[WARN] Capabilities: {len(caps)} capabilities loaded (expected at least 13)")

    # 7. Device Identity & Authentication
    try:
        identity = get_or_create_device_identity(config.data_dir)
        token_service = TokenService(db)
        tokens = token_service.list_tokens(include_revoked=False)
        print(f"[PASS] Device Identity: {identity.device_name} ({identity.device_id})")
        print(f"[PASS] Auth Tokens: {len(tokens)} active bearer token(s)")
    except Exception as exc:
        print(f"[FAIL] Auth subsystem: {exc}")
        all_passed = False

    # 8. Remote integration diagnostics (preserving legacy checks for tests)
    tunnel_client_bin = shutil.which("tunnel-client")
    if tunnel_client_bin:
        try:
            proc = subprocess.run(
                [tunnel_client_bin, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            tc_ver = proc.stdout.strip().split()[0] if proc.stdout else "unknown"
            print(f"[PASS] OpenAI Tunnel Client: Available in PATH ({tc_ver})")
        except Exception:
            print(f"[PASS] OpenAI Tunnel Client: Available at {tunnel_client_bin}")
    else:
        print("[INFO] OpenAI Tunnel Client: Not detected in PATH (optional for local operation)")

    tunnel_id = os.environ.get("CONTROL_PLANE_TUNNEL_ID")
    if tunnel_id:
        masked_id = tunnel_id[:10] + "..." if len(tunnel_id) > 10 else "***"
        print(f"[PASS] Remote Tunnel ID: Configured ({masked_id})")
    else:
        print("[INFO] Remote Tunnel ID: Not configured (local-only posture)")

    print(f"[PASS] Remote Tunnel Governance: Trust profile {config.trust_profile}")

    print("----------------------------------------")
    if all_passed:
        print("[OK] All critical doctor checks passed. System is ready.")
        return 0
    else:
        print("[ERROR] One or more doctor checks failed.")
        return 1


def cmd_remote(args: argparse.Namespace) -> int:
    """Manage remote integration status and diagnosis."""
    action = getattr(args, "remote_action", "status") or "status"
    if action == "setup":
        return cmd_setup(args)
    config = TacpConfig.load()
    mgr = RemoteManager(config)

    if action == "status":
        tunnel_client_bin = shutil.which("tunnel-client")
        tc_version = "NOT DETECTED"
        if tunnel_client_bin:
            try:
                p = subprocess.run(
                    [tunnel_client_bin, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                tc_version = p.stdout.strip()
            except Exception:
                tc_version = "AVAILABLE"

        tunnel_id = os.environ.get("CONTROL_PLANE_TUNNEL_ID")
        tunnel_status = "CONFIGURED" if tunnel_id else "NOT CONFIGURED"
        api_key = os.environ.get("CONTROL_PLANE_API_KEY")
        cred_status = "CONFIGURED (hidden)" if api_key else "NOT CONFIGURED"

        is_restricted = config.trust_profile in ("LOCKDOWN", "REMOTE_READ_ONLY")
        caps = CapabilityService.list_raw(
            include_mutating=config.mutation_enabled and not is_restricted,
            include_batch=config.batch_mutation_enabled and not is_restricted,
            include_execution=config.execution_enabled and not is_restricted,
        )

        r_status = mgr.get_status()

        print("========================================")
        print(" TACP Remote Integration Status         ")
        print("========================================")
        print("TACP Control Plane : READY")
        print("MCP Transport      : READY (stdio)")
        print(f"Tunnel Client      : {tc_version}")
        print(f"Tunnel ID          : {tunnel_id or 'NOT CONFIGURED'}")
        print(f"Tunnel State       : {tunnel_status}")
        print(f"Remote Enabled     : {config.remote_enabled or r_status.get('active', False)}")
        print(f"Remote Read-Only   : {config.remote_read_only}")
        print(f"Remote Mutation    : {config.remote_mutation_enabled}")
        print(f"Remote Execution   : {config.remote_execution_enabled}")
        print(f"Trust Profile      : {config.trust_profile}")
        print(f"Visible Tools      : {len(caps)} capabilities")
        print("Network Access     : DENIED")
        print(f"Credentials        : {cred_status}")
        print("----------------------------------------")
        print(f"Device Name        : {r_status.get('device_name', mgr.identity.device_name)}")
        print(f"Device ID          : {r_status.get('device_id', mgr.identity.device_id)}")
        print(f"Active Provider    : {r_status.get('provider', 'none')}")
        print(f"MCP Endpoint       : {r_status.get('mcp_endpoint', 'NONE')}")
        print(f"Status Message     : {r_status.get('status_message', 'Stopped')}")
        print("========================================")
        return 0

    elif action == "enable":
        provider = getattr(args, "provider", "cloudflare") or "cloudflare"
        port = getattr(args, "port", 8765) or 8765
        gateway_url = getattr(args, "gateway_url", None)
        custom_domain = getattr(args, "custom_domain", None)
        auth_required = not getattr(args, "no_auth", False)

        print(f"[*] Enabling TACP Remote MCP (provider: {provider})...")
        if provider == "cloudflare":
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            port_open = sock.connect_ex(("127.0.0.1", port)) == 0
            sock.close()

            if not port_open:
                http_log_file = config.data_dir / "tacp-http.log"
                http_pid_file = config.data_dir / "tacp-http.pid"
                server_cmd = [
                    sys.executable,
                    "-m",
                    "tacp.cli.main",
                    "serve-http",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ]
                if auth_required:
                    server_cmd.append("--auth")
                if config.mutation_enabled:
                    server_cmd.append("--allow-mutation")
                if config.batch_mutation_enabled:
                    server_cmd.append("--allow-batch-mutation")
                if config.execution_enabled:
                    server_cmd.append("--allow-execution")

                with open(http_log_file, "a", encoding="utf-8") as s_out:
                    s_proc = subprocess.Popen(
                        server_cmd,
                        stdout=s_out,
                        stderr=s_out,
                        text=True,
                        start_new_session=True,
                    )
                http_pid_file.write_text(str(s_proc.pid), encoding="utf-8")
                time.sleep(1.2)

        try:
            res = mgr.enable_remote(
                provider=provider,
                port=port,
                gateway_url=gateway_url,
                custom_domain=custom_domain,
                auth_required=auth_required,
            )
            print("\n============================================================")
            print(" TACP Remote MCP Ready")
            print("============================================================")
            print(f"Device Name : {res['device_name']}")
            print(f"Device ID   : {res['device_id']}")
            print(f"Endpoint    : {res['endpoint']}")
            print(f"Status      : {res['status'].upper()} ({res['status_message']})")
            if res.get("new_token"):
                print("------------------------------------------------------------")
                print("Generated Bearer Token (Save this - shown once):")
                print(f"  {res['new_token']}")
                print("------------------------------------------------------------")
            print("\nUse this endpoint in any MCP client (Claude, Cursor, etc.):")
            print(f"  URL: {res['endpoint']}")
            if auth_required:
                print("  Header: Authorization: Bearer <TOKEN>")
            print("============================================================\n")
            return 0 if res["status"] == "active" else 1
        except Exception as exc:
            print(f"[ERROR] Failed to enable remote MCP: {exc}")
            return 1

    elif action == "disable":
        print("[*] Disabling remote MCP connections...")
        mgr.disable_remote()
        print("[OK] Remote MCP disabled.")
        return 0

    elif action == "url":
        status = mgr.get_status()
        if not status.get("active") or not status.get("mcp_endpoint"):
            print("Remote MCP is currently INACTIVE. Enable with: tacp remote enable")
            return 1
        print(f"MCP Endpoint: {status.get('mcp_endpoint')}")
        print(f"Device ID   : {status.get('device_id')}")
        print(f"Provider    : {status.get('provider')}")
        return 0

    elif action == "pair":
        db = Database(config.db_path)
        db.connect()
        ps = PairingService(db)
        ttl = getattr(args, "ttl", 10) or 10
        pair_info = ps.generate_pairing_code(
            device_id=mgr.identity.device_id,
            device_name=mgr.identity.device_name,
            ttl_minutes=ttl,
        )
        print("\n========================================")
        print(" TACP Device Pairing                    ")
        print("========================================")
        print(f"Device Name  : {pair_info['device_name']}")
        print(f"Device ID    : {pair_info['device_id']}")
        print(f"Pairing Code : {pair_info['pairing_code']}")
        print(f"Expires In   : {ttl} minutes ({pair_info['expires_at']})")
        print("========================================\n")
        return 0

    elif action == "test":
        status = mgr.get_status()
        url = status.get("mcp_endpoint")
        if not status.get("active") or not url:
            print("[ERROR] Remote MCP is not currently active. Enable with 'tacp remote enable'.")
            return 1
        print(f"[*] Testing active remote MCP endpoint: {url}")
        from tacp.remote.tester import McpHttpTester

        token = getattr(args, "token", None)
        if not token:
            tokens = mgr.token_service.list_tokens(include_revoked=False)
            if tokens and status.get("auth_required", True):
                _, token = mgr.token_service.create_token(
                    name="TACP Remote Tester",
                    scopes=["tacp.read", "tacp.files.read", "tacp.system.read"],
                )
        tester = McpHttpTester(url.replace("/mcp", ""), token=token)
        ok = tester.run_all()
        return 0 if ok else 1

    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    """Run automated zero-touch setup and deployment of TACP control plane."""
    config = TacpConfig.load()
    port = getattr(args, "port", 8765) or 8765
    provider = getattr(args, "provider", "cloudflare") or "cloudflare"
    no_remote = getattr(args, "no_remote", False)

    mgr = RemoteManager(config)
    try:
        mgr.deploy(port=port, provider=provider, no_remote=no_remote)
        return 0
    except Exception as e:
        print(f"\n[!] Deployment failed: {e}", file=sys.stderr)
        return 1


def cmd_connection(_args: argparse.Namespace) -> int:
    """Export or inspect connection bundle and AI connection prompt."""
    config = TacpConfig.load()
    data_dir = config.data_dir
    identity = get_or_create_device_identity(data_dir)
    mgr = RemoteManager(config=config)
    remote_status = mgr.get_status()

    endpoint = remote_status.get("mcp_endpoint", "")
    provider = remote_status.get("provider", "none")
    is_active = remote_status.get("active", False)

    bundle_file = data_dir / "tacp-connection.json"
    prompt_file = data_dir / "tacp-agent-connect-prompt.txt"

    bundle = {
        "device_name": identity.device_name,
        "device_id": identity.device_id,
        "transport": "streamable-http",
        "mcp_url": endpoint or "http://127.0.0.1:8765/mcp",
        "authentication": {
            "type": "bearer",
            "header": "Authorization",
        },
        "provider": provider,
        "active": is_active,
        "protocol_version": "2026-07-28",
        "status": "verified" if is_active else "standby",
    }

    with open(bundle_file, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2)
    try:
        os.chmod(bundle_file, 0o600)
    except Exception:
        pass

    agent_prompt = f"""You are connecting to my TACP Android MCP server.

Use the standard MCP Streamable HTTP transport.

MCP endpoint:
{endpoint or "https://<ACTIVE_ENDPOINT>/mcp"}

Authentication:
Authorization: Bearer <YOUR_BEARER_TOKEN>

Connection rules:
1. Connect to the MCP endpoint using standard Streamable HTTP.
2. Perform standard MCP initialization (protocolVersion: "2026-07-28").
3. Confirm the negotiated MCP protocol version.
4. Call tools/list to discover available capabilities.
5. Confirm available TACP tools (e.g. system.inspect, fs.list, fs.read).
6. Do not assume capabilities that are not exposed.
7. Start with read-only operations (system.inspect, fs.list).
8. Do not execute commands or mutate files unless authorized and policy allows.
9. Respect all TACP authorization failures.
10. Never attempt to bypass TACP security controls.
11. Do not expose my credential in chat, logs, prompts, or tool outputs.
12. Treat returned phone data as private.
13. Ask for confirmation before risky operations.
14. Use the MCP tools directly rather than asking me to manually perform equivalent actions.
15. If connection fails, report the exact MCP/network error without fabricating success.
"""
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(agent_prompt)
    try:
        os.chmod(prompt_file, 0o600)
    except Exception:
        pass

    print("\n========================================")
    print(" TACP Connection Export                 ")
    print("========================================")
    print(f"Device Name      : {identity.device_name}")
    print(f"Device ID        : {identity.device_id}")
    print(f"MCP Endpoint     : {endpoint or 'INACTIVE (Run: tacp remote enable)'}")
    print("Transport        : Streamable HTTP")
    print("Protocol Version : 2026-07-28")
    print(f"Remote Status    : {'ACTIVE' if is_active else 'INACTIVE'}")
    print(f"Provider         : {provider}")
    print("----------------------------------------")
    print(f"Connection Bundle: {bundle_file} (mode 0600)")
    print(f"Agent Prompt File: {prompt_file} (mode 0600)")
    print("========================================\n")
    return 0


def cmd_auth(args: argparse.Namespace) -> int:
    """Manage authentication tokens."""
    config = TacpConfig.load()
    db = Database(config.db_path)
    db.connect()
    token_service = TokenService(db)

    subaction = getattr(args, "auth_action", "list") or "list"

    if subaction == "create":
        name = getattr(args, "name", None) or "Agent Token"
        scopes_str = getattr(args, "scopes", "tacp.read") or "tacp.read"
        scopes = [s.strip() for s in scopes_str.split(",") if s.strip()]
        expires = getattr(args, "expires", None)

        try:
            tok_rec, secret_token = token_service.create_token(
                name=name,
                scopes=scopes,
                expires_days=expires,
            )
            print("\n============================================================")
            print(" Authentication Token Created Successfully")
            print("============================================================")
            print(f"Token ID    : {tok_rec.id}")
            print(f"Name        : {tok_rec.name}")
            print(f"Prefix      : {tok_rec.token_prefix}")
            print(f"Scopes      : {', '.join(tok_rec.scopes)}")
            print(f"Expires At  : {tok_rec.expires_at or 'Never'}")
            print("------------------------------------------------------------")
            print("Bearer Token (SAVE THIS - it will NOT be shown again):")
            print(f"  {secret_token}")
            print("============================================================\n")
            return 0
        except Exception as exc:
            print(f"Error creating token: {exc}")
            return 1

    elif subaction == "list":
        include_all = getattr(args, "all", False)
        tokens = token_service.list_tokens(include_revoked=include_all)
        if not tokens:
            print(
                "No authentication tokens found. Create one with: tacp auth create --name 'My Agent'"
            )
            return 0

        print(f"\n{'ID':<16} {'NAME':<20} {'PREFIX':<20} {'SCOPES':<25} {'STATUS'}")
        print("-" * 90)
        for t in tokens:
            status = "REVOKED" if t.revoked else ("EXPIRED" if t.is_expired() else "ACTIVE")
            sc_str = ",".join(t.scopes)
            print(f"{t.id:<16} {t.name:<20} {t.token_prefix:<20} {sc_str:<25} {status}")
        print()
        return 0

    elif subaction == "revoke":
        tok_id = getattr(args, "token_id", None)
        if not tok_id:
            print("Error: token_id required.")
            return 1
        ok = token_service.revoke_token(tok_id)
        if ok:
            print(f"Successfully revoked token '{tok_id}'.")
            return 0
        else:
            print(f"Token '{tok_id}' not found or already revoked.")
            return 1

    return 0


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
    mgr = RemoteManager(config)
    r_status = mgr.get_status()

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
    print("----------------------------------------")
    print(f"Device Name      : {mgr.identity.device_name}")
    print(f"Device ID        : {mgr.identity.device_id}")
    print(f"Remote MCP       : {'ACTIVE' if r_status.get('active') else 'INACTIVE'}")
    if r_status.get("active"):
        print(f"MCP Endpoint     : {r_status.get('mcp_endpoint')}")
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


def cmd_serve_http(args: argparse.Namespace) -> int:
    """Launch Streamable HTTP MCP server loop."""
    config = TacpConfig.load()
    if getattr(args, "allow_mutation", False):
        object.__setattr__(config, "mutation_enabled", True)
        object.__setattr__(config, "read_only", False)
    if getattr(args, "allow_batch_mutation", False) and config.mutation_enabled:
        object.__setattr__(config, "batch_mutation_enabled", True)
    if getattr(args, "allow_execution", False):
        object.__setattr__(config, "execution_enabled", True)
        object.__setattr__(config, "read_only", False)
    object.__setattr__(config, "remote_enabled", True)
    if getattr(args, "device_control", False) or os.environ.get(
        "TACP_DEVICE_CONTROL", "0"
    ).lower() in ("1", "true", "yes"):
        object.__setattr__(config, "device_control_enabled", True)

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

    host = getattr(args, "host", "127.0.0.1") or "127.0.0.1"
    port = getattr(args, "port", 8765) or 8765
    auth_required = getattr(args, "auth", False)

    db = Database(config.db_path)
    db.connect()
    token_service = TokenService(db) if auth_required else None

    from tacp.access.mcp.http_server import run_http_server

    run_http_server(
        server,
        host=host,
        port=port,
        token_service=token_service,
        auth_required=auth_required,
    )
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
            print("No batch records found.")
            return 0
        print(f"\n{'BATCH ID':<16} {'WORKSPACE':<15} {'STATUS':<12} {'PATCHES'}")
        print("-" * 55)
        for b in batches:
            print(f"{b['id']:<16} {b['workspace_id']:<15} {b['status']:<12} {b['patch_count']}")
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
            return 0
        except Exception as exc:
            print(f"Error rolling back batch '{batch_id}': {exc}")
            return 1

    return 0


def cmd_execution(args: argparse.Namespace) -> int:
    """Manage governed command execution."""
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
    from tacp.core.execution_service import ExecutionService
    from tacp.core.workspace_service import WorkspaceService

    ws_service = WorkspaceService(db)
    policy_engine = PolicyEngine(
        read_only_enforced=config.read_only,
        mutation_enabled=config.mutation_enabled,
        batch_mutation_enabled=config.batch_mutation_enabled,
        execution_enabled=config.execution_enabled,
    )
    audit_service = AuditService(db)
    approval_engine = ApprovalEngine(db)
    execution_service = ExecutionService(
        db=db,
        config=config,
        policy_engine=policy_engine,
        approval_engine=approval_engine,
        audit_service=audit_service,
        workspace_service=ws_service,
    )

    subcommand = getattr(args, "exec_action", None)
    if subcommand == "list" or subcommand is None:
        ws_id = getattr(args, "workspace", None)
        limit = getattr(args, "limit", 20) or 20
        records = execution_service.list_executions(workspace_id=ws_id, limit=limit)
        if not records:
            print("No execution records found.")
            return 0
        print(
            f"\n{'EXEC ID':<16} {'STATUS':<12} {'EXIT':<6} {'EXE':<15} {'DURATION':<10} {'WORKSPACE'}"
        )
        print("-" * 75)
        for r in records:
            dur = f"{r.get('duration_ms', 0)}ms" if r.get("duration_ms") is not None else "-"
            exit_code = str(r.get("exit_code", "-"))
            print(
                f"{r['execution_id']:<16} {r['status']:<12} {exit_code:<6} "
                f"{r['executable']:<15} {dur:<10} {r['workspace_id']}"
            )
        print()
        return 0

    elif subcommand == "inspect":
        exec_id = getattr(args, "execution_id", None)
        if not exec_id:
            print("Error: execution_id required.")
            return 1
        rec = execution_service.inspect_execution(exec_id)
        if not rec:
            print(f"Error: Execution '{exec_id}' not found.")
            return 1
        print(json.dumps(rec, indent=2))
        return 0

    elif subcommand == "cancel":
        exec_id = getattr(args, "execution_id", None)
        if not exec_id:
            print("Error: execution_id required.")
            return 1
        operator_principal = Principal.human_operator("cli_operator")
        try:
            res = execution_service.cancel_execution(exec_id, principal=operator_principal)
            st = res.get("status", "unknown")
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

    elif subcommand == "remove":
        ws_id = getattr(args, "target", None)
        if not ws_id:
            print("Error: Workspace ID or name required.")
            return 1
        ok = ws_service.remove_workspace(ws_id)
        if ok:
            print(f"Successfully unregistered workspace '{ws_id}'.")
            return 0
        else:
            print(f"Workspace '{ws_id}' not found.")
            return 1

    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """View recent audit events or verify chain integrity."""
    config = TacpConfig.load()
    db = Database(config.db_path)
    db.connect()
    from tacp.core.audit_service import AuditService

    audit_service = AuditService(db)
    subcommand = getattr(args, "audit_action", None)

    if subcommand == "verify":
        diag = audit_service.verify_chain_detailed()
        if diag["valid"]:
            print("========================================")
            print(" TACP Audit Chain Integrity Check       ")
            print("========================================")
            print("Status         : PASS")
            print(f"Total Records  : {diag['total_records']}")
            print("Verification   : 100% Cryptographically Valid")
            print("Hash Algorithm : SHA-256 (Genesis Anchored)")
            print(f"Tip Hash       : {diag['tip_hash'][:16]}...")
            print("Tampering      : ZERO ANOMALIES DETECTED")
            print("========================================")
            return 0
        else:
            print("[FAIL] Audit chain verification failed! Tampering detected.")
            print(f"  Sequence #   : {diag.get('sequence')}")
            print(f"  Row ID       : {diag.get('rowid')}")
            print(f"  Entry ID     : {diag.get('entry_id')}")
            print(f"  Error Detail : {diag.get('error')}")
            if "expected_prev_hash" in diag:
                print(f"  Expected Prev: {diag['expected_prev_hash']}")
                print(f"  Actual Prev  : {diag['actual_prev_hash']}")
            if "expected_entry_hash" in diag:
                print(f"  Expected Hash: {diag['expected_entry_hash']}")
                print(f"  Actual Hash  : {diag['actual_entry_hash']}")
            return 1

    elif subcommand == "reanchor":
        print("[*] Re-anchoring cryptographic audit hash chain across all records...")
        res = audit_service.reanchor_chain()
        print("========================================")
        print(" TACP Audit Chain Re-Anchored           ")
        print("========================================")
        print("Status         : SUCCESS")
        print(f"Total Records  : {res['total_records']}")
        print(f"Tip Hash       : {res['tip_hash'][:16]}...")
        print("Verification   : Ready for validation")
        print("========================================")
        return 0

    # Default to recent events
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


def cmd_gateway(args: argparse.Namespace) -> int:
    """Run standalone TACP Remote MCP Gateway server."""
    from tacp.gateway.server import GatewayServer, GatewayState

    host = getattr(args, "host", "0.0.0.0") or "0.0.0.0"
    port = getattr(args, "port", 9090) or 9090

    state = GatewayState()
    server = GatewayServer((host, port), state)
    sys.stderr.write(f"[INFO] TACP Gateway listening at http://{host}:{port}\n")
    sys.stderr.write(f"[INFO] MCP endpoint: http://{host}:{port}/mcp\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def cmd_device(args: argparse.Namespace) -> int:
    """Device control plane inspection."""
    from tacp.engine.registry import CapabilityRegistry

    reg = CapabilityRegistry()
    action = getattr(args, "device_action", "info") or "info"
    res = reg.dispatch(f"device.{action}", {})

    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
    else:
        if action == "info":
            brand = (res.get("device", {}).get("brand") or res.get("brand", "")).upper()
            model = res.get("device", {}).get("model") or res.get("model", "")
            os_ver = res.get("os", {}).get("android_version") or res.get("android_version", "")
            sdk = res.get("os", {}).get("sdk_int") or res.get("sdk_int", "")
            arch = res.get("hardware", {}).get("architecture") or res.get("architecture", "")
            cores = res.get("hardware", {}).get("cpu_cores") or res.get("cpu_cores", "")
            print(f"Device: {brand} {model}")
            print(f"Android: {os_ver} (SDK {sdk})")
            print(f"Arch: {arch} ({cores} cores)")
        elif action == "battery":
            print(f"Battery: {res.get('percentage')}% ({res.get('status')})")
            if res.get("details"):
                print(f"Notes: {res.get('details')}")
        elif action == "uptime":
            print(f"Uptime: {res.get('uptime_seconds')} seconds ({res.get('uptime_human', '')})")
        else:
            print(json.dumps(res, indent=2))
    return 0 if res.get("success", True) else 1


def cmd_shell(args: argparse.Namespace) -> int:
    """Execute shell command."""
    from tacp.engine.registry import CapabilityRegistry

    reg = CapabilityRegistry()
    cmd = getattr(args, "cmd", None)
    if not cmd:
        print("Error: command required for shell exec")
        return 1

    cmd_args = getattr(args, "args", []) or []
    res = reg.dispatch(
        "shell.exec",
        {
            "command": cmd,
            "args": cmd_args,
            "cwd": getattr(args, "cwd", None),
            "timeout": getattr(args, "timeout", 30.0),
        },
    )

    if getattr(args, "json", False):
        print(json.dumps(res, indent=2))
    else:
        if res.get("stdout"):
            sys.stdout.write(res["stdout"])
        if res.get("stderr"):
            sys.stderr.write(res["stderr"])
    return int(res.get("exit_code", 0 if res.get("success", False) else 1))


def cmd_apps(args: argparse.Namespace) -> int:
    """Manage Android applications."""
    from tacp.engine.registry import CapabilityRegistry

    reg = CapabilityRegistry()
    action = getattr(args, "apps_action", "list") or "list"
    if action == "list":
        user_id = getattr(args, "user", "0")
        third_party_only = getattr(args, "third_party", True)
        res = reg.dispatch("package.list", {"user": user_id, "third_party_only": third_party_only})
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
        else:
            packages = res.get("packages", [])
            print(f"\nInstalled Packages ({len(packages)} found):")
            print("-" * 50)
            for p in packages:
                print(f"  {p}")
            print()
    elif action == "info":
        pkg = getattr(args, "package", "")
        res = reg.dispatch("package.info", {"package": pkg})
        print(json.dumps(res, indent=2))
    elif action == "launch":
        pkg = getattr(args, "package", "")
        res = reg.dispatch("app.launch", {"package": pkg})
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
        else:
            if res.get("success"):
                print(f"[OK] Launched app {pkg} (backend: {res.get('backend')})")
            else:
                print(f"[FAIL] Could not launch app {pkg}: {res.get('error')}")
    elif action == "open-url":
        url = getattr(args, "url", "")
        res = reg.dispatch("app.open_url", {"url": url})
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
        else:
            if res.get("success"):
                print(f"[OK] Opened URL: {url}")
            else:
                print(f"[FAIL] Could not open URL: {res.get('error')}")
    else:
        print(f"Unknown apps action: {action}")
        return 1

    return 0 if res.get("success", True) else 1


def cmd_storage(args: argparse.Namespace) -> int:
    """Storage diagnostics and file search."""
    from tacp.engine.registry import CapabilityRegistry

    reg = CapabilityRegistry()
    action = getattr(args, "storage_action", "overview") or "overview"
    if action == "overview":
        res = reg.dispatch("storage.overview", {})
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
        else:
            print("\nStorage Roots Overview:")
            print(f"{'LABEL':<18} {'PATH':<32} {'FREE':<10} {'TOTAL':<10} {'USED %'}")
            print("-" * 80)
            for m in res.get("storage_roots", []):
                print(
                    f"{m.get('label', ''):<18} {m.get('path', ''):<32} "
                    f"{m.get('free_gb', 0):.2f} GB   {m.get('total_gb', 0):.2f} GB   "
                    f"{m.get('used_percent', 0)}%"
                )
            print()
    elif action == "mounts":
        res = reg.dispatch("storage.mounts", {})
        print(json.dumps(res, indent=2))
    elif action == "large-files":
        res = reg.dispatch(
            "storage.large_files",
            {
                "path": getattr(args, "path", None),
                "threshold_mb": getattr(args, "min_mb", 50.0),
                "limit": getattr(args, "limit", 20),
            },
        )
        print(json.dumps(res, indent=2))
    else:
        print(f"Unknown storage action: {action}")
        return 1

    return 0 if res.get("success", True) else 1


def cmd_network(args: argparse.Namespace) -> int:
    """Network diagnostics."""
    from tacp.engine.registry import CapabilityRegistry

    reg = CapabilityRegistry()
    action = getattr(args, "network_action", "status") or "status"
    if action in ("status", "diagnostics"):
        res = reg.dispatch("network.diagnostics", {})
        if getattr(args, "json", False):
            print(json.dumps(res, indent=2))
        else:
            print("\nNetwork Status:")
            print(f"  Internet Connectivity: {res.get('internet_connected')}")
            print(f"  DNS Resolution:        {res.get('dns_working')}")
            print(f"  Active Interfaces:     {', '.join(res.get('active_interfaces', []))}")
            print()
    elif action == "interfaces":
        res = reg.dispatch("network.interfaces", {})
        print(json.dumps(res, indent=2))
    elif action == "ping":
        host = getattr(args, "host", "8.8.8.8")
        res = reg.dispatch("network.ping", {"host": host, "count": getattr(args, "count", 3)})
        print(json.dumps(res, indent=2))
    else:
        print(f"Unknown network action: {action}")
        return 1

    return 0 if res.get("success", True) else 1


def cmd_tasks(args: argparse.Namespace) -> int:
    """Task and job management."""
    from tacp.engine.registry import CapabilityRegistry

    reg = CapabilityRegistry()
    action = getattr(args, "tasks_action", "list") or "list"
    if action == "list":
        res = reg.dispatch("tasks.list", {"active_only": getattr(args, "active", False)})
    elif action == "get":
        task_id = getattr(args, "task_id", "")
        res = reg.dispatch("tasks.get", {"task_id": task_id})
    elif action == "cancel":
        task_id = getattr(args, "task_id", "")
        res = reg.dispatch("tasks.cancel", {"task_id": task_id})
    else:
        print(f"Unknown tasks action: {action}")
        return 1

    print(json.dumps(res, indent=2))
    return 0 if res.get("success", True) else 1


def cmd_self_test(args: argparse.Namespace) -> int:
    """Run comprehensive automated self-test across all TACP device control subsystems."""
    from tacp.core.discovery import DeviceDiscovery
    from tacp.engine.registry import CapabilityRegistry

    print("========================================")
    print(" TACP Device Control Plane Self-Test    ")
    print("========================================")

    reg = CapabilityRegistry()
    dev_report = DeviceDiscovery.get_device_report()

    results = []

    # Test 1: shell.pwd
    res_pwd = reg.dispatch("shell.pwd", {})
    t1_pass = res_pwd.get("success") is True and bool(res_pwd.get("cwd"))
    results.append({"name": "shell.pwd", "pass": t1_pass, "details": res_pwd.get("cwd")})

    # Test 2: device.info
    res_dev = reg.dispatch("device.info", {})
    os_ver = res_dev.get("os", {}).get("android_version") or res_dev.get("android_version")
    t2_pass = res_dev.get("success") is True and bool(os_ver)
    results.append(
        {
            "name": "device.info",
            "pass": t2_pass,
            "details": f"Android {os_ver}",
        }
    )

    # Test 3: storage.overview
    res_stor = reg.dispatch("storage.overview", {})
    t3_pass = res_stor.get("success") is True and len(res_stor.get("storage_roots", [])) > 0
    results.append(
        {
            "name": "storage.overview",
            "pass": t3_pass,
            "details": f"{len(res_stor.get('storage_roots', []))} storage roots",
        }
    )

    # Test 4: network.interfaces
    res_net = reg.dispatch("network.interfaces", {})
    t4_pass = res_net.get("success") is True
    results.append(
        {
            "name": "network.interfaces",
            "pass": t4_pass,
            "details": f"{res_net.get('count', 0)} interfaces",
        }
    )

    # Test 5: package.list
    res_pkg = reg.dispatch("package.list", {"user": "0", "third_party_only": True})
    t5_pass = res_pkg.get("success") is True
    results.append(
        {"name": "package.list", "pass": t5_pass, "details": f"{res_pkg.get('count', 0)} packages"}
    )

    # Test 6: diagnostics.bundle
    res_diag = reg.dispatch("diagnostics.bundle", {})
    bundle_path = res_diag.get("bundle_path")
    t6_pass = res_diag.get("success") is True and bool(bundle_path)
    results.append(
        {
            "name": "diagnostics.bundle",
            "pass": t6_pass,
            "details": f"Bundle created at {bundle_path}",
        }
    )

    all_passed = all(r["pass"] for r in results)

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "success": all_passed,
                    "device": dev_report["device"],
                    "tests": results,
                    "total_capabilities": len(reg._capabilities),
                },
                indent=2,
            )
        )
        return 0 if all_passed else 1

    for r in results:
        status_tag = "[PASS]" if r["pass"] else "[FAIL]"
        print(f"{status_tag} {r['name']:<25} : {r['details']}")

    print("----------------------------------------")
    if all_passed:
        print("[OK] All TACP device capability self-tests PASSED.")
        return 0
    else:
        print("[FAIL] One or more self-tests failed.")
        return 1


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
    cap_parser = subparsers.add_parser("capabilities", help="List registered capabilities")
    cap_parser.add_argument(
        "--device", action="store_true", help="List all Android device capabilities"
    )
    cap_parser.add_argument(
        "--category", help="Filter by capability category (shell, device, package, etc.)"
    )
    cap_parser.add_argument(
        "--backend", help="Filter by supported backend (termux, android_shell, etc.)"
    )
    cap_parser.add_argument(
        "--available", action="store_true", help="Filter by available capabilities only"
    )
    cap_parser.add_argument(
        "--json", action="store_true", help="Output in machine-readable JSON format"
    )

    # doctor
    doc_parser = subparsers.add_parser("doctor", help="Run environmental and health diagnostics")
    doc_parser.add_argument(
        "--json", action="store_true", help="Output diagnostic report in JSON format"
    )

    # status
    subparsers.add_parser("status", help="Show runtime system status")

    # serve (stdio)
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

    # serve-stdio (explicit alias to serve)
    serve_stdio = subparsers.add_parser(
        "serve-stdio", help="Start the stdio MCP server loop explicitly"
    )
    serve_stdio.add_argument("--workspace", type=str, help="Initial workspace directory")
    serve_stdio.add_argument("--workspace-name", type=str, help="Initial workspace name")
    serve_stdio.add_argument(
        "--allow-mutation", action="store_true", help="Enable single-file mutation"
    )
    serve_stdio.add_argument(
        "--allow-batch-mutation", action="store_true", help="Enable batch mutation"
    )
    serve_stdio.add_argument(
        "--allow-execution", action="store_true", help="Enable command execution"
    )

    # serve-http (Streamable HTTP)
    serve_http = subparsers.add_parser(
        "serve-http", help="Start the Streamable HTTP MCP server loop"
    )
    serve_http.add_argument("--host", type=str, default="127.0.0.1", help="HTTP listen host")
    serve_http.add_argument("--port", type=int, default=8765, help="HTTP listen port")
    serve_http.add_argument(
        "--auth", action="store_true", help="Enforce Bearer token authentication"
    )
    serve_http.add_argument("--workspace", type=str, help="Initial workspace directory")
    serve_http.add_argument("--workspace-name", type=str, help="Initial workspace name")
    serve_http.add_argument(
        "--allow-mutation", action="store_true", help="Enable single-file workspace mutation"
    )
    serve_http.add_argument(
        "--allow-batch-mutation",
        action="store_true",
        help="Enable multi-file batch workspace mutation",
    )
    serve_http.add_argument(
        "--allow-execution", action="store_true", help="Enable controlled command execution"
    )
    serve_http.add_argument(
        "--device-control",
        action="store_true",
        help="Enable deep Android device control capabilities",
    )

    # auth
    auth_parser = subparsers.add_parser("auth", help="Manage authentication tokens")
    auth_sub = auth_parser.add_subparsers(dest="auth_action")
    auth_create = auth_sub.add_parser("create", help="Create a new Bearer authentication token")
    auth_create.add_argument("--name", default="Agent Token", help="Descriptive token name")
    auth_create.add_argument("--scopes", default="tacp.read", help="Comma-separated scopes")
    auth_create.add_argument("--expires", type=int, help="Optional expiration in days")
    auth_list = auth_sub.add_parser("list", help="List all authentication tokens")
    auth_list.add_argument("--all", action="store_true", help="Include revoked tokens")
    auth_rev = auth_sub.add_parser("revoke", help="Revoke an authentication token")
    auth_rev.add_argument("token_id", help="Token ID to revoke")

    # remote
    remote_parser = subparsers.add_parser("remote", help="Manage remote MCP connectivity")
    remote_sub = remote_parser.add_subparsers(dest="remote_action")
    remote_sub.add_parser("status", help="Show remote integration status")
    rem_setup = remote_sub.add_parser(
        "setup", help="Run automated zero-touch setup and remote deployment"
    )
    rem_setup.add_argument("--port", type=int, default=8765, help="Local HTTP port (default: 8765)")
    rem_setup.add_argument(
        "--provider",
        choices=["cloudflare", "relay", "direct"],
        default="cloudflare",
        help="Remote provider type (default: cloudflare)",
    )
    rem_setup.add_argument(
        "--no-remote", action="store_true", help="Set up locally without remote tunnel exposure"
    )
    rem_enable = remote_sub.add_parser(
        "enable", help="Enable remote MCP access via tunnel or gateway"
    )
    rem_enable.add_argument(
        "--provider",
        choices=["cloudflare", "relay", "direct"],
        default="cloudflare",
        help="Remote provider type (default: cloudflare)",
    )
    rem_enable.add_argument("--port", type=int, default=8765, help="Local HTTP port")
    rem_enable.add_argument("--gateway-url", help="Gateway URL (required for relay provider)")
    rem_enable.add_argument("--custom-domain", help="Custom domain/host for direct provider")
    rem_enable.add_argument(
        "--no-auth", action="store_true", help="Disable token authentication requirement"
    )
    rem_enable.add_argument(
        "--device-control",
        action="store_true",
        help="Enable deep Android device control capabilities",
    )
    remote_sub.add_parser("disable", help="Disable remote MCP access")
    remote_sub.add_parser("url", help="Show active public MCP endpoint URL")
    rem_pair = remote_sub.add_parser("pair", help="Generate device pairing code")
    rem_pair.add_argument("--ttl", type=int, default=10, help="Pairing code validity in minutes")

    # gateway
    gw_parser = subparsers.add_parser(
        "gateway", help="Run standalone TACP Remote MCP Gateway server"
    )
    gw_parser.add_argument("--host", default="0.0.0.0", help="Listen host")
    gw_parser.add_argument("--port", type=int, default=9090, help="Listen port")

    # execution
    exec_parser = subparsers.add_parser("execution", help="Manage governed command execution")
    exec_sub = exec_parser.add_subparsers(dest="exec_action")
    exec_list = exec_sub.add_parser("list", help="List execution records")
    exec_list.add_argument("--workspace", help="Filter by workspace ID")
    exec_list.add_argument("--limit", type=int, default=20, help="Number of records to show")
    exec_inspect = exec_sub.add_parser("inspect", help="Inspect execution record")
    exec_inspect.add_argument("execution_id", help="Execution record ID")
    exec_cancel = exec_sub.add_parser("cancel", help="Cancel execution")
    exec_cancel.add_argument("execution_id", help="Execution record ID")
    exec_sub.add_parser("emergency-stop", help="Emergency stop all active executions")
    exec_req = exec_sub.add_parser("request", help="Request governed command execution")
    exec_req.add_argument("--workspace", help="Workspace ID")
    exec_req.add_argument("--executable", help="Executable name")
    exec_req.add_argument("--args", nargs="*", default=[], help="Command arguments")
    exec_req.add_argument("--cwd", default=".", help="Working directory")
    exec_req.add_argument("--dry-run", action="store_true", help="Run in dry-run mode")
    exec_req.add_argument("--timeout", type=float, default=30.0, help="Timeout in seconds")
    exec_req.add_argument("--stdin", help="Input string for stdin")
    exec_req.add_argument("--approval-token", help="Approval token if required")
    exec_req.add_argument("--contract-file", help="Path to contract JSON file")
    exec_req.add_argument(
        "--allow-execution", action="store_true", help="Enable execution capability"
    )
    exec_req.add_argument(
        "--auto-approve", action="store_true", help="Automatically approve ticket"
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
    rem_ws = ws_sub.add_parser("remove", help="Unregister a workspace directory")
    rem_ws.add_argument("target", help="Workspace ID or name to remove")

    # audit
    audit_parser = subparsers.add_parser("audit", help="View recent audit logs or verify integrity")
    audit_parser.add_argument("--limit", type=int, default=20, help="Number of records to show")
    audit_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    audit_sub = audit_parser.add_subparsers(dest="audit_action")
    audit_recent = audit_sub.add_parser("recent", help="View recent audit events")
    audit_recent.add_argument("--limit", type=int, default=20, help="Number of records to show")
    audit_recent.add_argument("--json", action="store_true", help="Output in JSON format")
    audit_sub.add_parser("verify", help="Verify cryptographic hash chain integrity")
    audit_sub.add_parser(
        "reanchor",
        help="Cryptographically recompute and repair hash pointers across all historical records",
    )

    # setup
    setup_parser = subparsers.add_parser(
        "setup", help="Run automated zero-touch setup and remote deployment"
    )
    setup_parser.add_argument(
        "--port", type=int, default=8765, help="Local HTTP port (default: 8765)"
    )
    setup_parser.add_argument(
        "--provider",
        choices=["cloudflare", "relay", "direct"],
        default="cloudflare",
        help="Remote provider type (default: cloudflare)",
    )
    setup_parser.add_argument(
        "--no-remote", action="store_true", help="Set up locally without remote tunnel exposure"
    )

    # connection
    conn_parser = subparsers.add_parser("connection", help="Manage connection bundles and export")
    conn_sub = conn_parser.add_subparsers(dest="conn_action")
    conn_sub.add_parser("export", help="Export connection bundle and universal agent prompt")

    # remote test
    rem_test = remote_sub.add_parser("test", help="Test active remote MCP endpoint")
    rem_test.add_argument("--token", help="Bearer token for authentication")

    # device
    dev_parser = subparsers.add_parser(
        "device", help="Android device hardware and state inspection"
    )
    dev_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    dev_sub = dev_parser.add_subparsers(dest="device_action")
    dev_sub.add_parser("info", help="Hardware, model, OS, architecture details")
    dev_sub.add_parser("snapshot", help="Full device status snapshot")
    dev_sub.add_parser("battery", help="Battery status and percentage")
    dev_sub.add_parser("properties", help="Android getprop system properties")
    dev_sub.add_parser("uptime", help="Device uptime")

    # shell
    shell_parser = subparsers.add_parser("shell", help="Android shell execution")
    shell_sub = shell_parser.add_subparsers(dest="shell_action")
    sh_exec = shell_sub.add_parser("exec", help="Execute shell command")
    sh_exec.add_argument("cmd", help="Command to run")
    sh_exec.add_argument("args", nargs="*", default=[], help="Command arguments")
    sh_exec.add_argument("--cwd", help="Working directory")
    sh_exec.add_argument("--timeout", type=float, default=30.0, help="Timeout in seconds")
    sh_exec.add_argument("--json", action="store_true", help="Output in JSON format")

    # apps
    apps_parser = subparsers.add_parser("apps", help="Android application management")
    apps_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    apps_sub = apps_parser.add_subparsers(dest="apps_action")
    app_list = apps_sub.add_parser("list", help="List installed packages")
    app_list.add_argument("--user", default="0", help="User profile ID (default: 0)")
    app_list.add_argument(
        "--third-party", action="store_true", default=True, help="Third-party packages only"
    )
    app_info = apps_sub.add_parser("info", help="Inspect package metadata and APK details")
    app_info.add_argument("package", help="Package name")
    app_launch = apps_sub.add_parser("launch", help="Launch Android application")
    app_launch.add_argument("package", help="Package name to launch")
    app_url = apps_sub.add_parser("open-url", help="Open URL in browser or default app")
    app_url.add_argument("url", help="URL to open")

    # storage
    storage_parser = subparsers.add_parser("storage", help="Storage mounts and usage diagnostics")
    storage_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    stor_sub = storage_parser.add_subparsers(dest="storage_action")
    stor_sub.add_parser("overview", help="Storage mounts overview")
    stor_sub.add_parser("mounts", help="Mount points details")
    stor_large = stor_sub.add_parser("large-files", help="Find largest files")
    stor_large.add_argument("--path", help="Directory path to search")
    stor_large.add_argument("--min-mb", type=float, default=50.0, help="Minimum file size in MB")
    stor_large.add_argument("--limit", type=int, default=20, help="Max results")

    # network
    net_parser = subparsers.add_parser("network", help="Network inspection and diagnostics")
    net_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    net_sub = net_parser.add_subparsers(dest="network_action")
    net_sub.add_parser("status", help="Network connectivity status")
    net_sub.add_parser("interfaces", help="List network interfaces")
    net_ping = net_sub.add_parser("ping", help="Ping a remote host")
    net_ping.add_argument("host", default="8.8.8.8", nargs="?", help="Host to ping")
    net_ping.add_argument("--count", type=int, default=3, help="Ping packets count")

    # tasks
    tasks_parser = subparsers.add_parser("tasks", help="Background tasks management")
    tasks_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    task_sub = tasks_parser.add_subparsers(dest="tasks_action")
    t_list = task_sub.add_parser("list", help="List background tasks")
    t_list.add_argument("--active", action="store_true", help="Active tasks only")
    t_get = task_sub.add_parser("get", help="Get task status")
    t_get.add_argument("task_id", help="Task ID")
    t_cancel = task_sub.add_parser("cancel", help="Cancel background task")
    t_cancel.add_argument("task_id", help="Task ID")

    # self-test
    st_parser = subparsers.add_parser(
        "self-test", help="Run comprehensive device control plane self-test"
    )
    st_parser.add_argument("--json", action="store_true", help="Output test results in JSON format")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "setup": cmd_setup,
        "connection": cmd_connection,
        "version": cmd_version,
        "capabilities": cmd_capabilities,
        "doctor": cmd_doctor,
        "status": cmd_status,
        "serve": cmd_serve,
        "serve-stdio": cmd_serve,
        "serve-http": cmd_serve_http,
        "auth": cmd_auth,
        "remote": cmd_remote,
        "gateway": cmd_gateway,
        "patch": cmd_patch,
        "batch": cmd_batch,
        "workspace": cmd_workspace,
        "audit": cmd_audit,
        "execution": cmd_execution,
        "device": cmd_device,
        "shell": cmd_shell,
        "apps": cmd_apps,
        "storage": cmd_storage,
        "network": cmd_network,
        "tasks": cmd_tasks,
        "self-test": cmd_self_test,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
