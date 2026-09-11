"""Unit tests for ExecutionContract immutability and canonical hashing."""

import pytest

from tacp.domain.execution import (
    ExecutionContract,
    ExecutionResult,
    ExecutionStatus,
    compute_execution_contract_hash,
)


def test_execution_contract_immutability() -> None:
    contract = ExecutionContract(
        workspace_id="ws-123",
        executable="/system/bin/printf",
        argv=("printf", "hello world"),
        cwd="/data/data/com.termux/files/home/projects/tacp",
        environment=(("LANG", "C.UTF-8"), ("PATH", "/system/bin")),
        network_enabled=False,
        timeout_seconds=15,
        max_stdout_bytes=65536,
        max_stderr_bytes=65536,
    )

    with pytest.raises(AttributeError):
        # Frozen dataclass must not allow mutation
        contract.executable = "/bin/sh"  # type: ignore[misc]

    with pytest.raises(AttributeError):
        contract.network_enabled = True  # type: ignore[misc]


def test_canonical_hash_determinism_and_sensitivity() -> None:
    c1 = ExecutionContract(
        workspace_id="ws-123",
        executable="/system/bin/printf",
        argv=("printf", "hello world"),
        cwd="/data/workspace",
        environment=(("PATH", "/system/bin"), ("LANG", "C.UTF-8")),
        network_enabled=False,
        timeout_seconds=15,
        max_stdout_bytes=65536,
        max_stderr_bytes=65536,
    )

    # Different env ordering must produce identical hash because keys are sorted
    c2 = ExecutionContract(
        workspace_id="ws-123",
        executable="/system/bin/printf",
        argv=("printf", "hello world"),
        cwd="/data/workspace",
        environment=(("LANG", "C.UTF-8"), ("PATH", "/system/bin")),
        network_enabled=False,
        timeout_seconds=15,
        max_stdout_bytes=65536,
        max_stderr_bytes=65536,
    )

    h1 = compute_execution_contract_hash(c1)
    h2 = compute_execution_contract_hash(c2)
    assert h1 == h2
    assert len(h1) == 64

    # Any parameter change must alter the hash
    c_diff_argv = ExecutionContract(
        workspace_id="ws-123",
        executable="/system/bin/printf",
        argv=("printf", "hello world!"),
        cwd="/data/workspace",
        environment=(("LANG", "C.UTF-8"), ("PATH", "/system/bin")),
        network_enabled=False,
        timeout_seconds=15,
        max_stdout_bytes=65536,
        max_stderr_bytes=65536,
    )
    assert compute_execution_contract_hash(c_diff_argv) != h1

    c_diff_cwd = ExecutionContract(
        workspace_id="ws-123",
        executable="/system/bin/printf",
        argv=("printf", "hello world"),
        cwd="/data/workspace/subdir",
        environment=(("LANG", "C.UTF-8"), ("PATH", "/system/bin")),
        network_enabled=False,
        timeout_seconds=15,
        max_stdout_bytes=65536,
        max_stderr_bytes=65536,
    )
    assert compute_execution_contract_hash(c_diff_cwd) != h1


def test_execution_result_serialization() -> None:
    res = ExecutionResult(
        execution_id="exec-abc12345",
        status=ExecutionStatus.SUCCEEDED.value,
        exit_code=0,
        stdout="hello\n",
        stderr="",
        duration_ms=45,
        contract_hash="0123456789abcdef",
    )
    d = res.to_dict()
    assert d["execution_id"] == "exec-abc12345"
    assert d["status"] == "SUCCEEDED"
    assert d["exit_code"] == 0
    assert d["stdout"] == "hello\n"
