"""Android Lifecycle State Machine for TACP.

Manages execution lifecycle states under Termux & Android OS conditions:
- DISCONNECTED: Not accepting external MCP requests
- CONNECTING: Transport / tunnel initialization in progress
- CONNECTED: Fully operational, companion connected, all lanes active
- DEGRADED: Companion disconnected or offline; core Termux MCP capabilities remain 100% active
- BACKGROUNDED: Termux process backgrounded / OS Doze mode; TTLs extended, aggressive polling paused
- SUSPENDED: System entering low-memory or thermal throttling state
"""

from __future__ import annotations

import enum
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class DeviceLifecycleState(str, enum.Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    BACKGROUNDED = "BACKGROUNDED"
    SUSPENDED = "SUSPENDED"


@dataclass(frozen=True)
class StateTransition:
    from_state: DeviceLifecycleState
    to_state: DeviceLifecycleState
    timestamp: float
    reason: str


class LifecycleManager:
    """Thread-safe device lifecycle coordinator."""

    def __init__(self, initial_state: DeviceLifecycleState = DeviceLifecycleState.CONNECTED) -> None:
        self._current_state = initial_state
        self._lock = threading.Lock()
        self._history: List[StateTransition] = []
        self._listeners: List[Callable[[DeviceLifecycleState, DeviceLifecycleState, str], None]] = []

    @property
    def current_state(self) -> DeviceLifecycleState:
        with self._lock:
            return self._current_state

    def transition_to(self, new_state: DeviceLifecycleState, reason: str = "") -> bool:
        """Execute state transition, notify listeners, and record transition."""
        with self._lock:
            if self._current_state == new_state:
                return False
            old_state = self._current_state
            self._current_state = new_state
            record = StateTransition(
                from_state=old_state,
                to_state=new_state,
                timestamp=time.time(),
                reason=reason,
            )
            self._history.append(record)
            logger.info("Device lifecycle transition: %s -> %s (reason: %s)", old_state.value, new_state.value, reason)

        # Notify listeners outside lock
        for listener in self._listeners:
            try:
                listener(old_state, new_state, reason)
            except Exception as e:
                logger.error("Lifecycle listener error: %s", e)
        return True

    def register_listener(self, fn: Callable[[DeviceLifecycleState, DeviceLifecycleState, str], None]) -> None:
        self._listeners.append(fn)

    def get_ttl_multiplier(self) -> float:
        """Return TTL multiplier based on lifecycle state to preserve battery in background."""
        st = self.current_state
        if st in (DeviceLifecycleState.BACKGROUNDED, DeviceLifecycleState.SUSPENDED):
            return 5.0  # 5x longer TTLs to suppress background wakeups
        return 1.0

    def get_status_report(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self._current_state.value,
                "ttl_multiplier": self.get_ttl_multiplier(),
                "recent_transitions": [
                    {
                        "from": t.from_state.value,
                        "to": t.to_state.value,
                        "timestamp": t.timestamp,
                        "reason": t.reason,
                    }
                    for t in self._history[-5:]
                ],
            }


_default_lifecycle_mgr: Optional[LifecycleManager] = None
_lifecycle_init_lock = threading.Lock()


def get_lifecycle_manager() -> LifecycleManager:
    global _default_lifecycle_mgr
    with _lifecycle_init_lock:
        if _default_lifecycle_mgr is None:
            _default_lifecycle_mgr = LifecycleManager()
        return _default_lifecycle_mgr
