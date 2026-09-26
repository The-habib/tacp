"""Unit tests for SingleFlight request coalescing."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

from tacp.core.coalesce import SingleFlight


def test_singleflight_coalescing() -> None:
    group = SingleFlight()
    execution_count = 0
    lock = threading.Lock()

    def expensive_operation() -> Dict[str, Any]:
        nonlocal execution_count
        with lock:
            execution_count += 1
        time.sleep(0.05)  # simulate work
        return {"result": "computed"}

    N = 50
    barrier = threading.Barrier(N)

    def worker() -> Dict[str, Any]:
        barrier.wait()
        return group.do("snapshot", expensive_operation)

    with ThreadPoolExecutor(max_workers=N) as ex:
        futures = [ex.submit(worker) for _ in range(N)]
        results = [f.result() for f in futures]

    assert len(results) == N
    for r in results:
        assert r == {"result": "computed"}

    # Exactly 1 underlying execution occurred
    assert execution_count == 1
    stats = group.stats()
    assert stats["total_invocations"] == N
    assert stats["underlying_executions"] == 1
    assert stats["coalesced_invocations"] == N - 1


def test_singleflight_error_propagation() -> None:
    group = SingleFlight()

    def failing_op() -> Any:
        time.sleep(0.02)
        raise ValueError("computation failed")

    N = 10
    barrier = threading.Barrier(N)

    def failing_worker() -> Any:
        barrier.wait()
        return group.do("fail_key", failing_op)

    exceptions = []
    with ThreadPoolExecutor(max_workers=N) as ex:
        futures = [ex.submit(failing_worker) for _ in range(N)]
        for f in futures:
            try:
                f.result()
            except Exception as e:
                exceptions.append(e)

    assert len(exceptions) == N
    assert all(isinstance(e, ValueError) for e in exceptions)
