"""Unit tests for ExecutionResolver (binary resolution, jailing, environment assembly)."""

import os
from pathlib import Path

import pytest

from tacp.core.execution_resolver import ExecutionResolver
from tacp.domain.errors import (
    TacpSecurityError,
    TacpValidationError,
)


def test_resolve_permitted_executable() -> None:
    resolver = ExecutionResolver()
    # "printf" or "echo" should resolve to existing binary
    resolved = resolver.resolve_executable("printf")
    assert Path(resolved).exists()
    assert os.access(resolved, os.X_OK)
    assert Path(resolved).name == "printf"


def test_resolve_forbidden_interpreters_and_tools() -> None:
    resolver = ExecutionResolver()
    forbidden = ["bash", "sh", "python", "python3", "node", "rm", "curl", "sudo"]
    for prog in forbidden:
        with pytest.raises(TacpSecurityError) as exc:
            resolver.resolve_executable(prog)
        assert "forbidden" in str(exc.value).lower() or "not permitted" in str(exc.value).lower()


def test_resolve_path_traversal() -> None:
    resolver = ExecutionResolver()
    with pytest.raises(TacpSecurityError):
        resolver.resolve_executable("../../bin/sh")


def test_resolve_working_directory_jailing(tmp_path: Path) -> None:
    resolver = ExecutionResolver()
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()
    subdir = ws_root / "subdir"
    subdir.mkdir()

    # Normal root
    assert resolver.resolve_working_directory(ws_root, None) == str(ws_root)
    assert resolver.resolve_working_directory(ws_root, "subdir") == str(subdir)

    # Traversal escape
    with pytest.raises(TacpSecurityError) as exc:
        resolver.resolve_working_directory(ws_root, "../")
    assert "escapes workspace boundary" in str(exc.value)

    # Non-existent directory
    with pytest.raises(TacpValidationError):
        resolver.resolve_working_directory(ws_root, "nonexistent")


def test_validate_argv() -> None:
    resolver = ExecutionResolver()
    # Normal argv
    argv = resolver.validate_argv("printf", ["printf", "hello", "world"])
    assert argv == ("printf", "hello", "world")

    # Empty argv
    with pytest.raises(TacpValidationError):
        resolver.validate_argv("printf", [])

    # Non-string element
    with pytest.raises(TacpValidationError):
        resolver.validate_argv("printf", ["printf", 123])  # type: ignore[list-item]

    # Null byte
    with pytest.raises(TacpSecurityError):
        resolver.validate_argv("printf", ["printf", "bad\x00arg"])


def test_assemble_environment_stripping(tmp_path: Path) -> None:
    resolver = ExecutionResolver()
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()

    caller_env = {
        "CUSTOM_VAR": "value1",
        "OPENAI_API_KEY": "sk-secret123",
        "AWS_SECRET_ACCESS_KEY": "aws-secret",
        "LD_PRELOAD": "/tmp/evil.so",
        "PYTHONPATH": "/tmp/lib",
    }

    env_pairs = resolver.assemble_environment(ws_root, str(ws_root), caller_env)
    env_dict = dict(env_pairs)

    # Base safe variables present
    assert "PATH" in env_dict
    assert env_dict["HOME"] == str(ws_root)
    assert env_dict["TERM"] == "dumb"
    assert env_dict["LANG"] == "C.UTF-8"

    # Safe variable allowed
    assert env_dict.get("CUSTOM_VAR") == "value1"

    # Dangerous variables stripped!
    assert "OPENAI_API_KEY" not in env_dict
    assert "AWS_SECRET_ACCESS_KEY" not in env_dict
    assert "LD_PRELOAD" not in env_dict
    assert "PYTHONPATH" not in env_dict
