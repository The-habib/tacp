"""Companion Transport Abstraction and Circuit Breaker (Phase 12, 16, 17).

Provides:
1. CompanionTransport ABC decoupling capability logic from local IPC.
2. HttpCompanionTransport with persistent HTTP connection reuse (keep-alive).
3. Resilient Circuit Breaker (CLOSED, OPEN, HALF_OPEN) preventing hang on disconnected companion.
4. Fail-fast error dispatching in < 0.1ms when companion is unavailable.
"""

from __future__ import annotations

import abc
import enum
import http.client
import json
import logging
import threading
import time
import uuid
from typing import Any, Dict, Optional

from tacp.domain.errors import ErrorCode, TacpError

logger = logging.getLogger(__name__)

COMPANION_PROTOCOL_VERSION = 1
MAX_PAYLOAD_BYTES = 10 * 1024 * 1024  # 10 MB maximum payload


class CircuitState(str, enum.Enum):
    CLOSED = "CLOSED"        # Normal operation
    OPEN = "OPEN"            # Failing fast, zero network attempts
    HALF_OPEN = "HALF_OPEN"  # Probing single canary request


class CompanionTransport(abc.ABC):
    """Abstract base class for TACP <-> Companion IPC transports."""

    @abc.abstractmethod
    def send_request(
        self,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        """Send an authenticated JSON request and return the JSON response."""
        pass

    @abc.abstractmethod
    def is_connected(self) -> bool:
        """Check if transport has active connectivity."""
        pass

    @abc.abstractmethod
    def close(self) -> None:
        """Close connection cleanly."""
        pass


class HttpCompanionTransport(CompanionTransport):
    """Persistent HTTP/1.1 transport with circuit breaker and connection reuse."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8766,
        auth_token: Optional[str] = None,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ) -> None:
        self.host = host
        self.port = port
        self.auth_token = auth_token
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._conn: Optional[http.client.HTTPConnection] = None
        self._lock = threading.RLock()
        self._connected = False

        # Circuit breaker state
        self._circuit_state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time = 0.0

    @property
    def circuit_state(self) -> CircuitState:
        with self._lock:
            if self._circuit_state == CircuitState.OPEN:
                if (time.time() - self._last_failure_time) >= self.recovery_timeout:
                    self._circuit_state = CircuitState.HALF_OPEN
                    return CircuitState.HALF_OPEN
            return self._circuit_state

    def _record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            self._circuit_state = CircuitState.CLOSED
            self._connected = True

    def _record_failure(self, reason: str = "") -> None:
        with self._lock:
            self._consecutive_failures += 1
            self._last_failure_time = time.time()
            self._connected = False
            if self._consecutive_failures >= self.failure_threshold or self._circuit_state == CircuitState.HALF_OPEN:
                self._circuit_state = CircuitState.OPEN
                logger.warning(
                    "Companion circuit breaker TRIPPED to OPEN (%d consecutive failures, host=%s:%d, reason=%s)",
                    self._consecutive_failures,
                    self.host,
                    self.port,
                    reason,
                )
                try:
                    from tacp.core.lifecycle import get_lifecycle_manager, DeviceLifecycleState
                    get_lifecycle_manager().transition_to(
                        DeviceLifecycleState.DEGRADED,
                        reason=f"Companion circuit tripped to OPEN: {reason}",
                    )
                except Exception:
                    pass

    def _get_connection(self, timeout: float) -> http.client.HTTPConnection:
        if self._conn is None:
            self._conn = http.client.HTTPConnection(
                self.host, self.port, timeout=timeout
            )
        return self._conn

    def is_connected(self) -> bool:
        if self.circuit_state == CircuitState.OPEN:
            return False
        return self._connected

    def send_request(
        self,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
    ) -> Dict[str, Any]:
        # 1. Evaluate Circuit Breaker Fail-Fast
        state = self.circuit_state
        if state == CircuitState.OPEN:
            raise TacpError(
                ErrorCode.UNAVAILABLE,
                f"Companion circuit breaker is OPEN (fail-fast, host={self.host}:{self.port})",
            )

        req_id = f"comp-{uuid.uuid4().hex[:8]}"
        body = json.dumps(payload or {}).encode("utf-8")
        if len(body) > MAX_PAYLOAD_BYTES:
            raise ValueError(f"Request payload exceeds max bound ({len(body)} > {MAX_PAYLOAD_BYTES})")

        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
            "Connection": "keep-alive",
            "X-Request-Id": req_id,
            "X-Companion-Protocol": str(COMPANION_PROTOCOL_VERSION),
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        method = "POST" if payload is not None else "GET"

        with self._lock:
            for attempt in range(2):
                try:
                    conn = self._get_connection(timeout)
                    conn.request(method, endpoint, body=body if method == "POST" else None, headers=headers)
                    resp = conn.getresponse()
                    resp_data = resp.read(MAX_PAYLOAD_BYTES + 1)
                    if len(resp_data) > MAX_PAYLOAD_BYTES:
                        raise ValueError("Response exceeded maximum allowable size of 10MB")

                    if resp.status >= 400:
                        err_msg = resp_data.decode("utf-8", errors="replace")
                        self._record_failure(f"HTTP {resp.status}")
                        raise TacpError(ErrorCode.PROVIDER_ERROR, f"Companion returned error HTTP {resp.status}: {err_msg}")

                    data = json.loads(resp_data.decode("utf-8"))
                    self._record_success()
                    return data

                except (http.client.RemoteDisconnected, BrokenPipeError, ConnectionResetError) as exc:
                    self.close()
                    if attempt == 1:
                        self._record_failure(str(exc))
                        raise TacpError(ErrorCode.UNAVAILABLE, f"Companion disconnected: {exc}") from exc
                except Exception as exc:
                    self.close()
                    self._record_failure(str(exc))
                    raise TacpError(ErrorCode.UNAVAILABLE, f"Companion connection failed on {endpoint}: {exc}") from exc

        return {}

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
            self._connected = False
            try:
                from tacp.core.state import DeviceStateManager
                DeviceStateManager.get_default().invalidate("companion")
            except Exception:
                pass
