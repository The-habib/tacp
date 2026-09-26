"""Multi-Lane Resource-Aware Admission Control for TACP.

Guarantees fair resource allocation and isolation across disparate operation profiles.
Prevents fast telemetry and read probes from starving behind slow mutations or companion timeouts.

Lanes:
- FAST_READ: 64 slots, 200ms timeout
- FILESYSTEM: 8 slots, 2s timeout
- PROCESS: 4 slots, 5s timeout
- COMPANION: 4 slots, 3s timeout
- MEDIA: 2 slots, 10s timeout
- MUTATION: 2 slots, 15s timeout
"""

from __future__ import annotations

import contextlib
import enum
import threading
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional

from tacp.domain.errors import ErrorCode, TacpError


class LaneType(str, enum.Enum):
    FAST_READ = "FAST_READ"
    FILESYSTEM = "FILESYSTEM"
    PROCESS = "PROCESS"
    COMPANION = "COMPANION"
    MEDIA = "MEDIA"
    MUTATION = "MUTATION"


@dataclass(frozen=True)
class LaneConfig:
    slots: int
    timeout: float


LANE_CONFIGS: Dict[LaneType, LaneConfig] = {
    LaneType.FAST_READ: LaneConfig(slots=64, timeout=0.200),
    LaneType.FILESYSTEM: LaneConfig(slots=8, timeout=2.0),
    LaneType.PROCESS: LaneConfig(slots=4, timeout=5.0),
    LaneType.COMPANION: LaneConfig(slots=4, timeout=3.0),
    LaneType.MEDIA: LaneConfig(slots=2, timeout=10.0),
    LaneType.MUTATION: LaneConfig(slots=2, timeout=15.0),
}


class AdmissionLane:
    """An isolated concurrency lane with bounded slots and wait timeouts."""

    __slots__ = (
        "lane_type",
        "slots",
        "timeout",
        "_sem",
        "_lock",
        "active_count",
        "queued_count",
        "rejected_count",
    )

    def __init__(self, lane_type: LaneType, config: LaneConfig) -> None:
        self.lane_type = lane_type
        self.slots = config.slots
        self.timeout = config.timeout
        self._sem = threading.Semaphore(self.slots)
        self._lock = threading.Lock()
        self.active_count = 0
        self.queued_count = 0
        self.rejected_count = 0

    def acquire(self, timeout_override: Optional[float] = None) -> bool:
        to = self.timeout if timeout_override is None else timeout_override
        with self._lock:
            self.queued_count += 1
        try:
            acquired = self._sem.acquire(timeout=to)
            with self._lock:
                self.queued_count -= 1
                if acquired:
                    self.active_count += 1
                else:
                    self.rejected_count += 1
            return acquired
        except Exception:
            with self._lock:
                self.queued_count -= 1
                self.rejected_count += 1
            return False

    def release(self) -> None:
        with self._lock:
            if self.active_count > 0:
                self.active_count -= 1
        self._sem.release()

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "slots": self.slots,
                "active": self.active_count,
                "queued": self.queued_count,
                "rejected": self.rejected_count,
            }


class AdmissionController:
    """Central multi-lane resource-aware admission controller."""

    def __init__(self, configs: Optional[Dict[LaneType, LaneConfig]] = None) -> None:
        self.configs = configs or LANE_CONFIGS
        self.lanes = {lane: AdmissionLane(lane, cfg) for lane, cfg in self.configs.items()}

    def classify(self, capability: str) -> LaneType:
        cap = (capability or "").lower().strip()
        if (
            cap
            in (
                "workspace.patch",
                "workspace.patch_batch",
                "execution.request",
                "package.install",
                "package.uninstall",
                "filesystem.write",
                "filesystem.delete",
            )
            or cap.startswith("device.action.create")
            or cap.startswith("input.inject")
        ):
            return LaneType.MUTATION

        if (
            cap.startswith("device.media")
            or cap.startswith("media.")
            or cap.startswith("device.camera")
        ):
            return LaneType.MEDIA

        if (
            cap.startswith("companion.")
            or cap.startswith("device.screen.capture")
            or cap.startswith("device.sensor")
            or cap.startswith("device.location")
        ):
            return LaneType.COMPANION

        if (
            cap.startswith("process.")
            or cap.startswith("device.process")
            or cap.startswith("execution.")
            or cap.startswith("shell.")
        ):
            return LaneType.PROCESS

        if (
            cap.startswith("filesystem.")
            or cap.startswith("device.file")
            or cap.startswith("workspace.")
        ):
            return LaneType.FILESYSTEM

        return LaneType.FAST_READ

    @contextlib.contextmanager
    def acquire(
        self, lane_or_capability: str | LaneType, timeout: Optional[float] = None
    ) -> Iterator[LaneType]:
        if isinstance(lane_or_capability, LaneType):
            lane_type = lane_or_capability
        else:
            lane_type = self.classify(lane_or_capability)

        lane = self.lanes[lane_type]
        if not lane.acquire(timeout):
            raise TacpError(
                ErrorCode.INTERNAL_ERROR,
                f"Concurrency admission timeout for lane {lane_type.value} ({lane.slots} slots)",
            )
        try:
            yield lane_type
        finally:
            lane.release()

    def stats(self) -> Dict[str, Any]:
        return {lane.value: lane_inst.stats() for lane, lane_inst in self.lanes.items()}


_default_controller: Optional[AdmissionController] = None
_controller_lock = threading.Lock()


def get_admission_controller() -> AdmissionController:
    global _default_controller
    with _controller_lock:
        if _default_controller is None:
            _default_controller = AdmissionController()
        return _default_controller
