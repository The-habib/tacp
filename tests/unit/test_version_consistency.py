"""Automated Release Identity and Version Consistency Test (Section 4).

Guarantees that:
package version == runtime version == metadata version == CLI version
"""

from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path

import pytest

from tacp import __version__
from tacp.access.mcp.protocol import McpRequest
from tacp.access.mcp.server import create_mcp_server
from tacp.cli.main import main
from tacp.core.system_service import SystemService
from tacp.infrastructure.config import TacpConfig


def normalize_version(ver: str) -> str:
    """Normalize PEP 440 release candidate format (e.g. 0.3.0rc1 -> 0.3.0-rc.1)."""
    clean = ver.strip().lstrip("v")
    # match 0.3.0rc1 or 0.3.0-rc.1 or 0.3.0.rc1
    m = re.match(r"^(\d+\.\d+\.\d+)[-.]?rc\.?(\d+)$", clean)
    if m:
        return f"{m.group(1)}-rc.{m.group(2)}"
    return clean


def test_authoritative_version_format() -> None:
    """Verify __version__ follows semantic versioning with optional release candidate."""
    pattern = r"^\d+\.\d+\.\d+(-rc\.\d+)?$"
    assert re.match(pattern, __version__), f"Invalid version string format: {__version__}"


def test_version_consistency_across_all_sources(
    repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """VERSION-CONSISTENCY-TEST: Fail if package, runtime, CLI, or metadata diverge."""
    authoritative = __version__
    normalized_authoritative = normalize_version(authoritative)

    # 1. Check pyproject.toml
    pyproject_path = repo_root / "pyproject.toml"
    assert pyproject_path.exists(), "pyproject.toml not found"
    pyproject_content = pyproject_path.read_text()
    match = re.search(r'version\s*=\s*"([^"]+)"', pyproject_content)
    assert match is not None, "Version not specified in pyproject.toml"
    pyproject_version = match.group(1)
    err_msg = (
        f"pyproject.toml version '{pyproject_version}' "
        f"does not match authoritative '{authoritative}'"
    )
    assert normalize_version(pyproject_version) == normalized_authoritative, err_msg

    # 2. Check importlib.metadata (installed distribution metadata)
    try:
        dist_version = importlib.metadata.version("tacp")
        assert normalize_version(dist_version) == normalized_authoritative, (
            f"Installed distribution version '{dist_version}' != '{authoritative}'"
        )
    except importlib.metadata.PackageNotFoundError:
        pass  # In standalone tests before install

    # 3. Check TacpConfig default
    config = TacpConfig()
    assert config.version == authoritative, (
        f"TacpConfig().version '{config.version}' != '{authoritative}'"
    )

    # 4. Check SystemService.get_version()
    sys_ver = SystemService.get_version()
    assert sys_ver["tacp_version"] == authoritative, (
        f"SystemService tacp_version '{sys_ver['tacp_version']}' != '{authoritative}'"
    )

    # 5. Check McpServer initialize response serverInfo
    server = create_mcp_server(config)
    resp = server.handle_request(McpRequest(method="initialize", params={}, id=1))
    assert resp is not None
    assert resp.result is not None
    mcp_ver = resp.result["serverInfo"]["version"]
    assert mcp_ver == authoritative, f"McpServer version '{mcp_ver}' != '{authoritative}'"

    # 6. Check CLI main(['version'])
    code = main(["version"])
    assert code == 0
    captured = capsys.readouterr()
    assert f"TACP v{authoritative}" in captured.out, (
        f"CLI output did not contain 'TACP v{authoritative}': {captured.out}"
    )
