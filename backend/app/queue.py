"""Arq job queue accessor for the API process.

Holds a single ArqRedis pool and exposes `enqueue` so endpoints can dispatch
work without owning connection lifecycle. The pool is created on first use
and closed at app shutdown.
"""
from __future__ import annotations

from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.jobs import Job, JobStatus

from app.config import settings

_pool: ArqRedis | None = None


async def get_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def enqueue(function_name: str, *args: Any) -> Job | None:
    pool = await get_pool()
    return await pool.enqueue_job(function_name, *args)


async def job_status(job_id: str) -> JobStatus:
    """Look up an Arq job's current status by id.

    Returns JobStatus.not_found when the worker that owned this job has
    crashed (or the result was evicted past `keep_result`). Either way,
    from the API's perspective the job is no longer making progress and
    the engagement attached to it should be considered orphaned.
    """
    pool = await get_pool()
    return await Job(job_id, pool).status()
