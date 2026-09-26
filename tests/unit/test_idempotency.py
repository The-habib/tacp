"""Unit tests for Mutation Idempotency."""

import pytest

from tacp.core.idempotency import IdempotencyManager
from tacp.domain.errors import ErrorCode, TacpError


def test_idempotent_execution_and_replay():
    mgr = IdempotencyManager(ttl_seconds=60.0)
    exec_count = 0

    def mutate():
        nonlocal exec_count
        exec_count += 1
        return {"status": "ok", "count": exec_count}

    key = "idem-test-001"
    params = {"path": "/file.txt", "content": "hello"}

    # First call
    res1 = mgr.execute(key, "workspace.patch", params, mutate)
    assert res1 == {"status": "ok", "count": 1}
    assert exec_count == 1
    assert "_idempotent_replay" not in res1

    # Second call with same key and params -> replayed from cache without re-executing
    res2 = mgr.execute(key, "workspace.patch", params, mutate)
    assert res2.get("status") == "ok"
    assert res2.get("count") == 1
    assert res2.get("_idempotent_replay") is True
    assert exec_count == 1  # Did NOT increment!


def test_mismatched_params_conflict():
    mgr = IdempotencyManager(ttl_seconds=60.0)
    key = "idem-test-002"

    mgr.execute(key, "workspace.patch", {"a": 1}, lambda: {"done": True})

    # Call with same key but different params -> CONFLICT error
    with pytest.raises(TacpError) as exc_info:
        mgr.execute(key, "workspace.patch", {"a": 2}, lambda: {"done": True})

    assert exc_info.value.code == ErrorCode.CONFLICT
    assert "mismatched parameters" in exc_info.value.message
