"""Unit tests for Multi-Lane Resource-Aware Admission Control."""

import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from tacp.core.admission import AdmissionController, LaneConfig, LaneType
from tacp.domain.errors import TacpError


def test_lane_classification() -> None:
    ac = AdmissionController()
    assert ac.classify("system.health") == LaneType.FAST_READ
    assert ac.classify("device.telemetry.snapshot") == LaneType.FAST_READ
    assert ac.classify("workspace.patch") == LaneType.MUTATION
    assert ac.classify("filesystem.read") == LaneType.FILESYSTEM
    assert ac.classify("process.list") == LaneType.PROCESS
    assert ac.classify("device.screen.capture") == LaneType.COMPANION
    assert ac.classify("device.media.audio_record") == LaneType.MEDIA


def test_fast_read_isolation_under_mutation_saturation() -> None:
    ac = AdmissionController(
        {
            LaneType.MUTATION: LaneConfig(slots=2, timeout=0.1),
            LaneType.FAST_READ: LaneConfig(slots=64, timeout=0.2),
            LaneType.FILESYSTEM: LaneConfig(slots=8, timeout=1.0),
            LaneType.PROCESS: LaneConfig(slots=4, timeout=1.0),
            LaneType.COMPANION: LaneConfig(slots=4, timeout=1.0),
            LaneType.MEDIA: LaneConfig(slots=2, timeout=1.0),
        }
    )

    # Saturate mutation lane with 2 slots holding for 0.2s
    mutation_started = []

    def slow_mutation() -> None:
        with ac.acquire(LaneType.MUTATION):
            mutation_started.append(True)
            time.sleep(0.2)

    ex = ThreadPoolExecutor(max_workers=10)
    f1 = ex.submit(slow_mutation)
    f2 = ex.submit(slow_mutation)

    # Wait for mutations to acquire their slots
    time.sleep(0.05)
    assert len(mutation_started) == 2

    # Fast read must acquire IMMEDIATELY and NOT block on saturated mutation lane!
    t0 = time.perf_counter()
    with ac.acquire(LaneType.FAST_READ):
        read_duration = time.perf_counter() - t0

    assert read_duration < 0.01  # < 10ms
    f1.result()
    f2.result()
    ex.shutdown(wait=True)


def test_admission_timeout() -> None:
    ac = AdmissionController(
        {
            LaneType.MUTATION: LaneConfig(slots=1, timeout=0.05),
            LaneType.FAST_READ: LaneConfig(slots=1, timeout=0.05),
            LaneType.FILESYSTEM: LaneConfig(slots=1, timeout=0.05),
            LaneType.PROCESS: LaneConfig(slots=1, timeout=0.05),
            LaneType.COMPANION: LaneConfig(slots=1, timeout=0.05),
            LaneType.MEDIA: LaneConfig(slots=1, timeout=0.05),
        }
    )

    def hold() -> None:
        with ac.acquire(LaneType.MUTATION):
            time.sleep(0.15)

    ex = ThreadPoolExecutor(max_workers=2)
    f1 = ex.submit(hold)
    time.sleep(0.02)

    # Second caller should time out
    with pytest.raises(TacpError) as exc_info:
        with ac.acquire(LaneType.MUTATION):
            pass

    assert "Concurrency admission timeout" in str(exc_info.value)
    f1.result()
    ex.shutdown(wait=True)
