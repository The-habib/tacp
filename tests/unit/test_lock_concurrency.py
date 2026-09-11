"""Concurrency, ownership, and TTL race tests for LockService (Sections 17, 18, 19, 38)."""

import concurrent.futures
import time

import pytest

from tacp.core.lock_service import LockService
from tacp.domain.errors import TacpConflictError
from tacp.infrastructure.database import Database


def test_lock_concurrent_race_exactly_one_winner(test_db: Database) -> None:
    """Race test: 10 concurrent threads racing to acquire the same resource lock."""
    lock_service = LockService(test_db)
    resource_id = "ws-1:critical_file.py"

    num_threads = 10
    successes = []
    conflicts = []

    def attempt_acquire(worker_id: int) -> tuple[str, str]:
        owner = f"worker-{worker_id}"
        try:
            tok = lock_service.acquire_lock(resource_id=resource_id, owner_id=owner, ttl_seconds=10)
            return ("SUCCESS", tok)
        except TacpConflictError as exc:
            return ("CONFLICT", str(exc))

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(attempt_acquire, i) for i in range(num_threads)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    for status, msg in results:
        if status == "SUCCESS":
            successes.append(msg)
        else:
            conflicts.append(msg)

    # Invariant: EXACTLY 1 thread acquires the lock
    assert len(successes) == 1, f"Expected 1 winner, got {len(successes)}"
    # Invariant: The other 9 threads get TacpConflictError
    assert len(conflicts) == num_threads - 1


def test_lock_ownership_enforcement(test_db: Database) -> None:
    """Invariant: Only the authentic owner with the matching token can release the lock."""
    lock_service = LockService(test_db)
    resource = "ws-sec:config.json"

    # Owner Alice acquires lock
    token_alice = lock_service.acquire_lock(resource, owner_id="alice", ttl_seconds=20)

    # 1. Foreign owner Bob cannot release Alice's lock even if Bob guesses token
    released_by_bob = lock_service.release_lock(resource, token=token_alice, owner_id="bob")
    assert released_by_bob is False

    # 2. Alice cannot release with a wrong token
    released_wrong_token = lock_service.release_lock(
        resource,
        token="tacp_lock_fake",  # noqa: S106
        owner_id="alice",
    )
    assert released_wrong_token is False

    # 3. Alice releases with matching owner_id and token
    released_alice = lock_service.release_lock(resource, token=token_alice, owner_id="alice")
    assert released_alice is True


def test_stale_lock_cannot_release_new_owner(test_db: Database) -> None:
    """Invariant: Stale token from previous expired lock cannot release new owner's lock."""
    lock_service = LockService(test_db)
    resource = "ws-sec:state.json"

    # Owner 1 acquires lock with 0-second TTL (immediately expires)
    token_stale = lock_service.acquire_lock(resource, owner_id="owner-old", ttl_seconds=0)
    time.sleep(0.01)

    # Owner 2 acquires the now-expired resource
    token_new = lock_service.acquire_lock(resource, owner_id="owner-new", ttl_seconds=30)
    assert token_new != token_stale

    # Owner 1 attempts to release with old stale token
    released = lock_service.release_lock(resource, token=token_stale, owner_id="owner-old")
    assert released is False

    # Owner 2's lock must still be active and intact
    with pytest.raises(TacpConflictError):
        lock_service.acquire_lock(resource, owner_id="third-party", ttl_seconds=10)

    # Owner 2 successfully releases
    assert lock_service.release_lock(resource, token=token_new, owner_id="owner-new") is True


def test_lock_lease_renewal(test_db: Database) -> None:
    """Invariant: Lock owner can renew active lease before TTL expires."""
    lock_service = LockService(test_db)
    resource = "ws-sec:batch.py"

    token = lock_service.acquire_lock(resource, owner_id="worker-batch", ttl_seconds=5)

    # Refresh active lock succeeds
    refreshed = lock_service.refresh_lock(
        resource, token=token, owner_id="worker-batch", additional_seconds=15
    )
    assert refreshed is True

    # Refresh with wrong owner or wrong token fails
    assert (
        lock_service.refresh_lock(
            resource,
            token="fake_token",  # noqa: S106
            owner_id="worker-batch",
        )
        is False
    )
    assert lock_service.refresh_lock(resource, token=token, owner_id="wrong-owner") is False
