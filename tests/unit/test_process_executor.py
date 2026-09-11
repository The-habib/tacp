"""Unit tests for ProcessExecutor (process groups, timeouts, stream bounding, sanitization)."""

from pathlib import Path

from tacp.core.execution_resolver import ExecutionResolver
from tacp.domain.execution import ExecutionContract, ExecutionStatus
from tacp.providers.process_executor import ProcessExecutor, sanitize_output


def test_sanitize_output() -> None:
    # Strips ANSI color sequences
    raw = "\x1b[31mError:\x1b[0m failed\x1b[2J"
    cleaned = sanitize_output(raw)
    assert cleaned == "Error: failed"

    # Normalizes carriage returns
    raw_cr = "line1\r\nline2\rline3\n"
    assert sanitize_output(raw_cr) == "line1\nline2\nline3\n"

    # Replaces null byte
    assert sanitize_output("null\x00byte") == "null\ufffdbyte"


def test_execute_printf_success(tmp_path: Path) -> None:
    resolver = ExecutionResolver()
    executor = ProcessExecutor()

    bin_path = resolver.resolve_executable("printf")
    contract = ExecutionContract(
        workspace_id="ws-test",
        executable=bin_path,
        argv=("printf", "hello %s\n", "world"),
        cwd=str(tmp_path),
        environment=(("LANG", "C.UTF-8"), ("PATH", "/system/bin:/bin")),
        network_enabled=False,
        timeout_seconds=5,
        max_stdout_bytes=65536,
        max_stderr_bytes=65536,
    )

    result = executor.execute("exec-test-1", contract)
    assert result.status == ExecutionStatus.SUCCEEDED.value
    assert result.exit_code == 0
    assert result.stdout == "hello world\n"
    assert result.stderr == ""
    assert result.timed_out is False
    assert result.stdout_truncated is False


def test_execute_stdout_bounding(tmp_path: Path) -> None:
    resolver = ExecutionResolver()
    executor = ProcessExecutor()

    bin_path = resolver.resolve_executable("printf")
    # Generates 100 characters: "AAAAAAAAAAAAAAAA..."
    contract = ExecutionContract(
        workspace_id="ws-test",
        executable=bin_path,
        argv=("printf", "%s", "A" * 100),
        cwd=str(tmp_path),
        environment=(("LANG", "C.UTF-8"), ("PATH", "/system/bin:/bin")),
        network_enabled=False,
        timeout_seconds=5,
        max_stdout_bytes=20,  # Bound to 20 bytes
        max_stderr_bytes=65536,
    )

    result = executor.execute("exec-test-2", contract)
    assert result.status == ExecutionStatus.SUCCEEDED.value
    assert len(result.stdout) == 20
    assert result.stdout_truncated is True
