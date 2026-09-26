"""Unit tests for Companion Transport Circuit Breaker and Lifecycle transitions."""

import time
import pytest
from tacp.backends.companion_transport import HttpCompanionTransport, CircuitState
from tacp.core.lifecycle import get_lifecycle_manager, DeviceLifecycleState
from tacp.domain.errors import ErrorCode, TacpError


def test_circuit_breaker_tripping():
    # Use non-existent port to force immediate connection refusal
    transport = HttpCompanionTransport(port=59999, failure_threshold=3, recovery_timeout=0.2)
    assert transport.circuit_state == CircuitState.CLOSED

    # 3 consecutive failed requests should trip circuit to OPEN
    for _ in range(3):
        with pytest.raises(TacpError):
            transport.send_request("/test", timeout=0.05)

    assert transport.circuit_state == CircuitState.OPEN
    assert not transport.is_connected()
    assert get_lifecycle_manager().current_state == DeviceLifecycleState.DEGRADED

    # In OPEN state, requests fail fast in < 0.1ms (no network connection attempted)
    t0 = time.perf_counter()
    with pytest.raises(TacpError) as exc_info:
        transport.send_request("/test")
    duration_ms = (time.perf_counter() - t0) * 1000.0

    assert exc_info.value.code == ErrorCode.UNAVAILABLE
    assert "circuit breaker is OPEN" in exc_info.value.message
    assert duration_ms < 1.0 # sub-millisecond fail-fast!

    # Wait for recovery timeout to transition to HALF_OPEN
    time.sleep(0.25)
    assert transport.circuit_state == CircuitState.HALF_OPEN
