"""Global test configuration and fixtures for TACP."""

from pathlib import Path
from typing import Any, Generator

import pytest

from tacp.access.mcp.server import McpServer
from tacp.access.mcp.tools import McpToolRegistry
from tacp.control.policy import PolicyEngine
from tacp.core.audit_service import AuditService
from tacp.core.capability_service import CapabilityService
from tacp.core.filesystem_service import FilesystemService
from tacp.core.process_service import ProcessService
from tacp.core.system_service import SystemService
from tacp.core.workspace_service import WorkspaceService
from tacp.infrastructure.config import OutputLimits, TacpConfig
from tacp.infrastructure.database import Database
from tacp.providers.filesystem import FilesystemProvider
from tacp.providers.process import ProcessProvider


@pytest.fixture
def repo_root() -> Path:
    """Return the absolute Path to the repository root."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def fixtures_dir(repo_root: Path) -> Path:
    """Return the path to the test fixtures directory."""
    return repo_root / "tests" / "fixtures"


@pytest.fixture
def temp_tacp_dir(tmp_path: Path) -> Path:
    """Return an isolated directory for TACP state."""
    tacp_dir = tmp_path / "tacp_data"
    tacp_dir.mkdir(parents=True, exist_ok=True)
    return tacp_dir


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Create a sample workspace with known files."""
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "hello.txt").write_text("Hello TACP World!\n")
    (ws / "notes.md").write_text("# Project Notes\nSample content here.\n")
    sub = ws / "subdir"
    sub.mkdir()
    (sub / "nested.txt").write_text("Nested content.\n")
    return ws


@pytest.fixture
def test_config(temp_tacp_dir: Path, temp_workspace: Path) -> TacpConfig:
    """Return a test TacpConfig pointing to temporary paths."""
    return TacpConfig(
        data_dir=temp_tacp_dir,
        db_path=temp_tacp_dir / "test_tacp.db",
        log_level="DEBUG",
        read_only=True,
        limits=OutputLimits(
            max_file_read_bytes=1024,
            max_dir_entries=10,
            max_search_results=10,
            max_processes=10,
            max_audit_results=10,
        ),
        allowed_workspace_roots=[temp_workspace],
    )


@pytest.fixture
def test_db(test_config: TacpConfig) -> Generator[Database, None, None]:
    """Return an initialized test database."""
    db = Database(test_config.db_path)
    db.connect()
    yield db
    db.close()


@pytest.fixture
def test_services(
    test_config: TacpConfig, test_db: Database, temp_workspace: Path
) -> dict[str, Any]:
    """Return a dictionary of all initialized services."""
    audit_service = AuditService(test_db)
    policy_engine = PolicyEngine(read_only_enforced=test_config.read_only)
    workspace_service = WorkspaceService(test_db)
    ws = workspace_service.register_workspace(name="test-ws", root_path=temp_workspace)

    fs_provider = FilesystemProvider(limits=test_config.limits)
    filesystem_service = FilesystemService(workspace_service, fs_provider)

    proc_provider = ProcessProvider(limits=test_config.limits)
    process_service = ProcessService(proc_provider)

    system_service = SystemService(test_db)
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

    mcp_server = McpServer(tool_registry=tool_registry, config=test_config)

    return {
        "config": test_config,
        "db": test_db,
        "audit_service": audit_service,
        "policy_engine": policy_engine,
        "workspace_service": workspace_service,
        "filesystem_service": filesystem_service,
        "process_service": process_service,
        "system_service": system_service,
        "capability_service": capability_service,
        "tool_registry": tool_registry,
        "mcp_server": mcp_server,
        "workspace": ws,
    }
