"""Automated security audit for forbidden secret patterns in tracked files."""

import re
from pathlib import Path

FORBIDDEN_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z]+ PRIVATE KEY-----"),
    re.compile(r"ghp_[A-Za-z0-9_]{36,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{82,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{32,}"),
]

IGNORED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}


def test_no_secrets_in_repository_files(repo_root: Path) -> None:
    """Ensure no tracked repository file contains obvious active private keys or tokens."""
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        # Skip synthetic test fixture
        if "synthetic_secret.txt" in path.name:
            continue

        content = path.read_text(errors="ignore")
        for pattern in FORBIDDEN_PATTERNS:
            match = pattern.search(content)
            assert match is None, f"Potential secret pattern found in {path}: {pattern.pattern}"
