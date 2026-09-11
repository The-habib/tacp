"""Unit tests for LockService (Category M & H)."""

import pytest

from tacp.core.lock_service import LockService
from tacp.domain.errors import TacpConflictError
from tacp.infrastructure.database import Database


@pytest.fixture
def lock_service(test_db: Database) -> LockService:
    return LockService(test_db)


def test_acquire_and_release_lock(lock_service: LockService) -> None:
    token = lock_service.acquire_lock("ws-1:src/main.py", "owner-1", ttl_seconds=10)
    assert token.startswith("tacp_lock_")

    released = lock_service.release_lock("ws-1:src/main.py", token)
    assert released is True

    # Releasing again should return False
    released_again = lock_service.release_lock("ws-1:src/main.py", token)
    assert released_again is False


def test_lock_conflict_raises_error(lock_service: LockService) -> None:
    token = lock_service.acquire_lock("ws-1:src/main.py", "owner-1", ttl_seconds=30)
    assert token

    with pytest.raises(TacpConflictError) as exc:
        lock_service.acquire_lock("ws-1:src/main.py", "owner-2", ttl_seconds=30)
    assert "locked by 'owner-1'" in str(exc.value)


def test_expired_lock_can_be_acquired(lock_service: LockService) -> None:
    # Acquire with ttl_seconds = -5 (already expired)
    token1 = lock_service.acquire_lock("ws-1:src/main.py", "owner-1", ttl_seconds=-5)
    assert token1

    # Should succeed because previous lock is expired
    token2 = lock_service.acquire_lock("ws-1:src/main.py", "owner-2", ttl_seconds=10)
    assert token2
    assert token1 != token2


def test_hold_context_manager(lock_service: LockService) -> None:
    with lock_service.hold("ws-1:src/app.py", "owner-1", ttl_seconds=10) as token:
        assert token.startswith("tacp_lock_")
        # Attempting to acquire inside block should fail
        with pytest.raises(TacpConflictError):
            lock_service.acquire_lock("ws-1:src/app.py", "owner-2", ttl_seconds=10)

    # After exiting block, resource is unlocked
    token2 = lock_service.acquire_lock("ws-1:src/app.py", "owner-2", ttl_seconds=10)
    assert token2


def test_hold_context_manager_cleans_up_on_exception(lock_service: LockService) -> None:
    try:
        with lock_service.hold("ws-1:src/crash.py", "owner-1", ttl_seconds=10):
            raise RuntimeError("Something failed")
    except RuntimeError:
        pass

    # Resource should be released despite exception
    token = lock_service.acquire_lock("ws-1:src/crash.py", "owner-2", ttl_seconds=10)
    assert token
