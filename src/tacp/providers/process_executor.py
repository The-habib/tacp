"""Process Executor.

Governed OS process execution provider with process groups, timeouts, and bounded streams.
"""

from __future__ import annotations

import logging
import os
import re
import select
import signal
import subprocess
import time
from typing import Optional, Tuple

from tacp.domain.execution import ExecutionContract, ExecutionResult, ExecutionStatus

logger = logging.getLogger(__name__)

# Regex for stripping ANSI escape codes and terminal controls
ANSI_ESCAPE_PATTERN = re.compile(
    r"\x1B(?:[@-Z\\_]|\[[0-?]*[ -/]*[@-~]|\][^\x07\x1B]*(?:\x07|\x1B\\))"
)


def sanitize_output(raw: str) -> str:
    """Sanitize process output to prevent terminal injection and formatting corruption."""
    if not raw:
        return ""
    # Strip ANSI escape sequences
    cleaned = ANSI_ESCAPE_PATTERN.sub("", raw)
    # Normalize carriage returns
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    # Replace null bytes
    cleaned = cleaned.replace("\x00", "\ufffd")
    return cleaned


class ProcessExecutor:
    """Spawns and manages governed operating system processes."""

    def __init__(self) -> None:
        pass

    def execute(
        self,
        execution_id: str,
        contract: ExecutionContract,
    ) -> ExecutionResult:
        """Execute a process under strict process-group isolation, timeouts, and bounded I/O."""
        env = dict(contract.environment)
        start_mono = time.monotonic()

        try:
            # Stage 14: Spawn process in a new session (setsid)
            process = subprocess.Popen(  # noqa: S603
                args=list(contract.argv),
                executable=contract.executable,
                cwd=contract.cwd,
                env=env,
                shell=False,
                start_new_session=True,  # Sets new session & PGID = PID
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True,
            )
        except OSError as exc:
            duration_ms = int((time.monotonic() - start_mono) * 1000)
            return ExecutionResult(
                execution_id=execution_id,
                status=ExecutionStatus.FAILED.value,
                exit_code=getattr(exc, "errno", 1) or 1,
                stdout="",
                stderr=f"Failed to spawn process: {exc}",
                duration_ms=duration_ms,
            )

        pid = process.pid
        pgid = pid  # Under start_new_session=True, pgid is guaranteed == pid

        # Read bounded streams and monitor timeout
        stdout_data, stderr_data, stdout_trunc, stderr_trunc, timed_out, term_sig = (
            self._monitor_and_reap(
                process=process,
                pgid=pgid,
                timeout_seconds=contract.timeout_seconds,
                max_stdout=contract.max_stdout_bytes,
                max_stderr=contract.max_stderr_bytes,
            )
        )

        duration_ms = int((time.monotonic() - start_mono) * 1000)

        # Determine final status
        exit_code = process.returncode
        if timed_out:
            status = ExecutionStatus.TIMED_OUT.value
        elif term_sig is not None and term_sig != 0:
            status = ExecutionStatus.FAILED.value
        elif exit_code == 0:
            status = ExecutionStatus.SUCCEEDED.value
        else:
            status = ExecutionStatus.FAILED.value

        clean_stdout = sanitize_output(stdout_data.decode("utf-8", errors="replace"))
        clean_stderr = sanitize_output(stderr_data.decode("utf-8", errors="replace"))

        return ExecutionResult(
            execution_id=execution_id,
            status=status,
            exit_code=exit_code,
            stdout=clean_stdout,
            stderr=clean_stderr,
            duration_ms=duration_ms,
            stdout_truncated=stdout_trunc,
            stderr_truncated=stderr_trunc,
            timed_out=timed_out,
            cancelled=False,
            pid=pid,
            pgid=pgid,
            term_signal=term_sig,
        )

    def _monitor_and_reap(
        self,
        process: subprocess.Popen[bytes],
        pgid: int,
        timeout_seconds: int,
        max_stdout: int,
        max_stderr: int,
    ) -> Tuple[bytes, bytes, bool, bool, bool, Optional[int]]:
        """Read stdout/stderr with byte caps and kill process group on timeout."""
        stdout_buf = bytearray()
        stderr_buf = bytearray()
        stdout_trunc = False
        stderr_trunc = False
        timed_out = False
        term_signal: Optional[int] = None

        assert process.stdout is not None
        assert process.stderr is not None

        # Configure non-blocking reads
        os.set_blocking(process.stdout.fileno(), False)
        os.set_blocking(process.stderr.fileno(), False)

        deadline = time.monotonic() + timeout_seconds
        read_set = [process.stdout, process.stderr]

        while read_set and time.monotonic() < deadline:
            timeout_left = max(0.01, min(0.5, deadline - time.monotonic()))
            try:
                rlist, _, _ = select.select(read_set, [], [], timeout_left)
            except (ValueError, OSError):
                break

            for fd in rlist:
                chunk = fd.read(4096)
                if not chunk:
                    # EOF reached on this stream
                    read_set.remove(fd)
                    continue

                if fd is process.stdout:
                    if len(stdout_buf) + len(chunk) <= max_stdout:
                        stdout_buf.extend(chunk)
                    else:
                        remaining = max_stdout - len(stdout_buf)
                        if remaining > 0:
                            stdout_buf.extend(chunk[:remaining])
                        stdout_trunc = True
                elif fd is process.stderr:
                    if len(stderr_buf) + len(chunk) <= max_stderr:
                        stderr_buf.extend(chunk)
                    else:
                        remaining = max_stderr - len(stderr_buf)
                        if remaining > 0:
                            stderr_buf.extend(chunk[:remaining])
                        stderr_trunc = True

            # If process has exited and no more output ready, break early
            if process.poll() is not None and not rlist:
                break

        # Check for timeout
        if time.monotonic() >= deadline and process.poll() is None:
            timed_out = True
            term_signal = self._kill_process_group(pgid, process)
        else:
            # Process finished or is terminating; wait for completion
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                term_signal = self._kill_process_group(pgid, process)

        # Drain any remaining bytes (up to limit)
        try:
            rem_out = process.stdout.read()
            if rem_out:
                if len(stdout_buf) + len(rem_out) <= max_stdout:
                    stdout_buf.extend(rem_out)
                else:
                    stdout_trunc = True
        except (OSError, ValueError):
            pass

        try:
            rem_err = process.stderr.read()
            if rem_err:
                if len(stderr_buf) + len(rem_err) <= max_stderr:
                    stderr_buf.extend(rem_err)
                else:
                    stderr_trunc = True
        except (OSError, ValueError):
            pass

        process.stdout.close()
        process.stderr.close()

        if term_signal is None and process.returncode is not None and process.returncode < 0:
            term_signal = -process.returncode

        return (
            bytes(stdout_buf),
            bytes(stderr_buf),
            stdout_trunc,
            stderr_trunc,
            timed_out,
            term_signal,
        )

    def _kill_process_group(self, pgid: int, process: subprocess.Popen[bytes]) -> int:
        """Terminate entire process group with SIGTERM then SIGKILL."""
        # 1. Send SIGTERM to process group
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return signal.SIGTERM

        # 2. Wait up to 1.5s grace period
        grace_deadline = time.monotonic() + 1.5
        while time.monotonic() < grace_deadline:
            if process.poll() is not None:
                return signal.SIGTERM
            time.sleep(0.05)

        # 3. Send SIGKILL to process group if still alive
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

        try:
            process.wait(timeout=1.0)
        except (subprocess.TimeoutExpired, OSError):
            pass

        return signal.SIGKILL
