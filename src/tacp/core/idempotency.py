"""Mutation idempotency and replay caching for TACP.

Guarantees that retry-safe mutating requests with an Idempotency-Key
(e.g., from network retries or agent re-submissions) return the deterministic,
identical result without re-executing side effects.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from tacp.domain.errors import ErrorCode, TacpError


@dataclass
class IdempotencyRecord:
    key: str
    capability: str
    request_hash: str
    response: Dict[str, Any]
    timestamp: float
    status: str  # "IN_FLIGHT" | "COMPLETED" | "FAILED"


class IdempotencyManager:
    """Thread-safe idempotency coordinator with bounded TTL."""

    def __init__(self, ttl_seconds: float = 3600.0) -> None:
        self.ttl = ttl_seconds
        self._records: Dict[str, IdempotencyRecord] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_key_lock(self, key: str) -> threading.Lock:
        with self._global_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]

    @staticmethod
    def compute_hash(params: Dict[str, Any]) -> str:
        serialized = json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def execute(
        self,
        idempotency_key: str,
        capability: str,
        params: Dict[str, Any],
        fn: Callable[[], Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Execute mutating operation with strict idempotency semantics."""
        if not idempotency_key:
            return fn()

        req_hash = self.compute_hash(params)
        key_lock = self._get_key_lock(idempotency_key)

        with key_lock:
            record = self._records.get(idempotency_key)
            now = time.time()

            if record is not None:
                # Expired record eviction
                if (now - record.timestamp) > self.ttl:
                    self._records.pop(idempotency_key, None)
                    record = None
                else:
                    if record.request_hash != req_hash:
                        raise TacpError(
                            ErrorCode.CONFLICT,
                            f"Idempotency key '{idempotency_key}' reused with mismatched parameters",
                        )
                    if record.status == "COMPLETED":
                        cached_copy = dict(record.response)
                        cached_copy["_idempotent_replay"] = True
                        return cached_copy
                    elif record.status == "IN_FLIGHT":
                        raise TacpError(
                            ErrorCode.CONFLICT,
                            f"Concurrent request in-flight for idempotency key '{idempotency_key}'",
                        )

            # Register as IN_FLIGHT
            self._records[idempotency_key] = IdempotencyRecord(
                key=idempotency_key,
                capability=capability,
                request_hash=req_hash,
                response={},
                timestamp=now,
                status="IN_FLIGHT",
            )

        # Execute outside lock
        try:
            result = fn()
            with key_lock:
                self._records[idempotency_key] = IdempotencyRecord(
                    key=idempotency_key,
                    capability=capability,
                    request_hash=req_hash,
                    response=result,
                    timestamp=time.time(),
                    status="COMPLETED",
                )
            return result
        except Exception:
            with key_lock:
                self._records.pop(idempotency_key, None)
            raise


_default_idempotency_mgr: Optional[IdempotencyManager] = None
_idempotency_init_lock = threading.Lock()


def get_idempotency_manager() -> IdempotencyManager:
    global _default_idempotency_mgr
    with _idempotency_init_lock:
        if _default_idempotency_mgr is None:
            _default_idempotency_mgr = IdempotencyManager()
        return _default_idempotency_mgr
