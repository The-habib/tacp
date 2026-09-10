"""Global test configuration and fixtures for TACP."""

from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    """Return the absolute Path to the repository root."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def fixtures_dir(repo_root: Path) -> Path:
    """Return the path to the test fixtures directory."""
    return repo_root / "tests" / "fixtures"
