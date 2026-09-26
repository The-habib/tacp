"""Unit tests for Cancellation and Deadline Propagation."""

import time
import threading
import pytest
from tacp.control.identity import RequestContext
from tacp.domain.errors import ErrorCode, TacpError


def test_deadline_expired():
    # Deadline in the past
    ctx = RequestContext(
        capability="system.inspect",
        deadline_monotonic=time.monotonic() - 0.1,
    )
    assert ctx.is_cancelled()
    assert ctx.remaining_timeout() == 0.0

    with pytest.raises(TacpError) as exc_info:
        ctx.check_cancelled()
    assert exc_info.value.code == ErrorCode.DEADLINE_EXCEEDED


def test_deadline_valid():
    # Deadline in the future
    ctx = RequestContext(
        capability="system.inspect",
        deadline_monotonic=time.monotonic() + 10.0,
    )
    assert not ctx.is_cancelled()
    rem = ctx.remaining_timeout()
    assert rem is not None and rem > 5.0
    ctx.check_cancelled()  # Should not raise


def test_cancellation_event():
    cancel_evt = threading.Event()
    ctx = RequestContext(
        capability="system.inspect",
        cancellation_event=cancel_evt,
    )
    assert not ctx.is_cancelled()
    ctx.check_cancelled()

    cancel_evt.set()
    assert ctx.is_cancelled()
    with pytest.raises(TacpError) as exc_info:
        ctx.check_cancelled()
    assert exc_info.value.code == ErrorCode.CANCELLED
