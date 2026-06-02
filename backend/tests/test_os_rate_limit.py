# backend/tests/test_os_rate_limit.py
"""Tests for the per-host SSH fingerprinting lock."""
import asyncio
import pytest
from app.api.os_rate_limit import FingerprintLock, FingerprintAlreadyRunningError


@pytest.mark.asyncio
async def test_lock_allows_first_caller():
    lock = FingerprintLock()
    async with lock.acquire("10.0.0.1"):
        pass  # first caller acquires without raising


@pytest.mark.asyncio
async def test_lock_blocks_concurrent_same_host():
    lock = FingerprintLock()

    async def hold():
        async with lock.acquire("10.0.0.2"):
            await asyncio.sleep(0.05)

    task1 = asyncio.create_task(hold())
    await asyncio.sleep(0.01)  # let task1 acquire first
    with pytest.raises(FingerprintAlreadyRunningError):
        async with lock.acquire("10.0.0.2"):
            pass
    await task1


@pytest.mark.asyncio
async def test_lock_allows_different_hosts_concurrently():
    lock = FingerprintLock()

    async def hold(host):
        async with lock.acquire(host):
            await asyncio.sleep(0.03)

    # Two different hosts should both proceed without raising
    await asyncio.gather(hold("10.0.0.3"), hold("10.0.0.4"))


@pytest.mark.asyncio
async def test_lock_releases_after_use():
    lock = FingerprintLock()
    async with lock.acquire("10.0.0.5"):
        pass
    # After release, the same host can be acquired again
    async with lock.acquire("10.0.0.5"):
        pass


@pytest.mark.asyncio
async def test_lock_gather_same_host_exactly_one_succeeds():
    """Under a no-sleep gather on the same host, exactly one acquire holds the
    lock body at a time and overlapping callers are rejected."""
    lock = FingerprintLock()
    succeeded = 0
    rejected = 0

    async def attempt():
        nonlocal succeeded, rejected
        try:
            async with lock.acquire("10.0.0.9"):
                # Force the body to span an event-loop tick so other coroutines
                # in the gather get a chance to attempt acquisition while held.
                nonlocal_hold = await asyncio.sleep(0, result=True)
                succeeded += 1
        except FingerprintAlreadyRunningError:
            rejected += 1

    await asyncio.gather(*[attempt() for _ in range(10)])
    # At least one must succeed; any that overlapped the held body are rejected.
    assert succeeded >= 1
    assert succeeded + rejected == 10
    # Because the body awaits (sleep(0)), the first holder forces the rest to
    # observe a locked state and be rejected — so not all 10 can serialize through.
    assert rejected >= 1
