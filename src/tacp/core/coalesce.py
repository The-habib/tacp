"""Request coalescing and single-flight stampede prevention for TACP.

Ensures that when multiple concurrent requests query an expensive or expired resource,
only a single underlying execution occurs, while all other callers block and share the result.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

T = TypeVar("T")


class _Call:
    __slots__ = ("val", "err", "event", "dups")

    def __init__(self) -> None:
        self.val: Any = None
        self.err: Optional[Exception] = None
        self.event = threading.Event()
        self.dups: int = 0


class SingleFlight:
    """Thread-safe single-flight execution group."""

    def __init__(self) -> None:
        self._calls: Dict[str, _Call] = {}
        self._lock = threading.Lock()
        self.total_invocations: int = 0
        self.coalesced_invocations: int = 0
        self.underlying_executions: int = 0

    def do(self, key: str, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute fn under key, coalescing concurrent invocations."""
        with self._lock:
            self.total_invocations += 1
            if key in self._calls:
                call = self._calls[key]
                call.dups += 1
                self.coalesced_invocations += 1
                wait = True
            else:
                call = _Call()
                self._calls[key] = call
                self.underlying_executions += 1
                wait = False

        if wait:
            call.event.wait()
            if call.err is not None:
                raise call.err
            return call.val

        try:
            call.val = fn(*args, **kwargs)
            return call.val
        except Exception as exc:
            call.err = exc
            raise
        finally:
            with self._lock:
                self._calls.pop(key, None)
                call.event.set()

    def stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "total_invocations": self.total_invocations,
                "coalesced_invocations": self.coalesced_invocations,
                "underlying_executions": self.underlying_executions,
            }


_default_group: Optional[SingleFlight] = None
_group_lock = threading.Lock()


def get_singleflight_group() -> SingleFlight:
    global _default_group
    with _group_lock:
        if _default_group is None:
            _default_group = SingleFlight()
        return _default_group
