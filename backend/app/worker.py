"""Arq worker.

Runs the long-lived engagement pipelines in a separate process so they
survive uvicorn restarts and so the API can scale horizontally without
each replica owning the pipelines for engagements it happens to launch.

Run with:
    arq app.worker.WorkerSettings

Tasks publish events through ws.progress.broadcast, which writes to
Postgres for replay and PUBLISHes to a Redis channel that connected
WebSocket clients (in any API replica) subscribe to.
"""
from __future__ import annotations

import logging
import uuid

from arq.connections import RedisSettings

from app.api.start import (
    _judge_findings_async,
    _run_codebase_pipeline,
    _run_cve_pipeline,
    _run_web_pipeline,
)
from app.config import settings

logger = logging.getLogger(__name__)


async def run_web_pipeline(ctx: dict, engagement_id: str) -> None:
    await _run_web_pipeline(uuid.UUID(engagement_id))


async def run_codebase_pipeline(ctx: dict, engagement_id: str) -> None:
    await _run_codebase_pipeline(uuid.UUID(engagement_id))


async def run_cve_pipeline(ctx: dict, engagement_id: str) -> None:
    await _run_cve_pipeline(uuid.UUID(engagement_id))


async def judge_findings(ctx: dict, engagement_id: str, finding_ids: list[str]) -> None:
    await _judge_findings_async(engagement_id, [uuid.UUID(fid) for fid in finding_ids])


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


class WorkerSettings:
    functions = [run_web_pipeline, run_codebase_pipeline, run_cve_pipeline, judge_findings]
    redis_settings = _redis_settings()
    # Pipelines can take many minutes (LLM calls, dep installs in Docker,
    # diff-execute) so push the job timeout out from the default 5 min.
    job_timeout = 60 * 30
    max_jobs = 4
    keep_result = 60 * 60
