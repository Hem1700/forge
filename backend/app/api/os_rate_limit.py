# backend/app/api/os_rate_limit.py
"""Per-host lock: prevent concurrent SSH fingerprinting of the same host.

In-process async lock keyed by host string. Protects SSH targets from being
hammered by two simultaneous fingerprint scans (a soft DoS guard). Scoped to a
single worker process — sufficient because OS pipelines run in the Arq worker.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager


class FingerprintAlreadyRunningError(Exception):
    """Raised when a fingerprint scan is already running for the given host."""

    def __init__(self, host: str):
        super().__init__(f"A fingerprint scan is already running for host: {host}")
        self.host = host


class FingerprintLock:
    """In-process async lock keyed by host string."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, host: str):
        async with self._guard:
            lock = self._locks.get(host)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[host] = lock
            if lock.locked():
                raise FingerprintAlreadyRunningError(host)
        async with lock:
            yield


# Module-level singleton shared across all pipeline coroutines in this worker process.
_fingerprint_lock = FingerprintLock()
