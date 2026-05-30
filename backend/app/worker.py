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
from datetime import datetime, timedelta

from arq.connections import RedisSettings
from arq.cron import cron
from arq.jobs import JobStatus
from sqlalchemy import select, update

from app.api.start import (
    _judge_findings_async,
    _run_codebase_pipeline,
    _run_cve_pipeline,
    _run_github_pipeline,
    _run_os_pipeline,
    _run_web_pipeline,
)
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.engagement import Engagement, EngagementStatus
from app.queue import job_status
from app.ws import progress as ws_progress

logger = logging.getLogger(__name__)


async def _recover_orphaned_engagements(ctx: dict) -> None:
    """On worker startup, find running engagements whose Arq job is gone and
    mark them failed so users aren't left with engagements stuck in 'running'
    forever after a worker restart/crash."""
    cutoff = datetime.utcnow() - timedelta(hours=1)
    failed: list[tuple[str, str]] = []

    try:
        async with AsyncSessionLocal() as db:
            running = (
                await db.execute(
                    select(Engagement).where(Engagement.status == EngagementStatus.running)
                )
            ).scalars().all()

            for e in running:
                should_fail = False
                reason = ""
                if e.job_id:
                    try:
                        status = await job_status(e.job_id)
                    except Exception:
                        logger.exception("worker startup: job_status lookup failed for %s", e.id)
                        continue
                    if status == JobStatus.not_found:
                        should_fail = True
                        reason = "worker restarted; job not found in queue"
                elif e.started_at and e.started_at < cutoff:
                    should_fail = True
                    reason = "stale running engagement recovered on worker startup"

                if should_fail:
                    e.status = EngagementStatus.aborted
                    failed.append((str(e.id), reason))

            await db.commit()
    except Exception:
        logger.exception("worker startup: orphan recovery sweep failed")
        return

    for eid, reason in failed:
        try:
            await ws_progress.broadcast(eid, "engagement_aborted", {
                "engagement_id": eid,
                "reason": reason,
            })
        except Exception:
            logger.exception("worker startup: failed to broadcast abort for %s", eid)
        logger.warning("worker startup: aborted orphaned engagement %s — %s", eid, reason)


async def refresh_trivy_db(ctx: dict) -> None:
    """Daily cron: refresh local Trivy vulnerability database."""
    import asyncio
    try:
        proc = await asyncio.create_subprocess_exec(
            "trivy", "image", "--download-db-only", "--quiet",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode == 0:
            logger.info("Trivy DB refreshed successfully")
        else:
            logger.warning("Trivy DB refresh failed: %s", stderr.decode()[:200])
    except FileNotFoundError:
        logger.warning("refresh_trivy_db: trivy binary not found in PATH")
    except asyncio.TimeoutError:
        logger.warning("refresh_trivy_db: trivy download timed out after 300s")
    except Exception:
        logger.exception("refresh_trivy_db: unexpected error")


async def reset_monthly_budgets(ctx: dict) -> None:
    """Daily cron: reset current_spend_usd for orgs whose reset_day matches today."""
    from sqlalchemy import text
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text(
                    "UPDATE org_budgets SET current_spend_usd = 0, updated_at = NOW() "
                    "WHERE reset_day = EXTRACT(DAY FROM NOW())::int "
                    "RETURNING org_id"
                )
            )
            reset_orgs = result.fetchall()
            await db.commit()
        if reset_orgs:
            logger.info("Monthly budget reset for %d orgs", len(reset_orgs))
    except Exception:
        logger.exception("Monthly budget reset cron failed")


async def run_web_pipeline(ctx: dict, engagement_id: str) -> None:
    await _run_web_pipeline(uuid.UUID(engagement_id))


async def run_codebase_pipeline(ctx: dict, engagement_id: str) -> None:
    await _run_codebase_pipeline(uuid.UUID(engagement_id))


async def run_github_pipeline(ctx: dict, engagement_id: str) -> None:
    await _run_github_pipeline(uuid.UUID(engagement_id))


async def run_cve_pipeline(ctx: dict, engagement_id: str) -> None:
    await _run_cve_pipeline(uuid.UUID(engagement_id))


async def judge_findings(ctx: dict, engagement_id: str, finding_ids: list[str], org_id: str | None = None) -> None:
    await _judge_findings_async(
        engagement_id,
        [uuid.UUID(fid) for fid in finding_ids],
        org_id=uuid.UUID(org_id) if org_id else None,
    )


async def run_os_pipeline(ctx: dict, engagement_id: str, org_id: str | None = None) -> None:
    await _run_os_pipeline(
        uuid.UUID(engagement_id),
        org_id=uuid.UUID(org_id) if org_id else None,
    )


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


HEALTH_CHECK_KEY = "arq:queue:health-check"


class WorkerSettings:
    functions = [run_web_pipeline, run_codebase_pipeline, run_cve_pipeline, judge_findings, run_os_pipeline, run_github_pipeline]
    on_startup = _recover_orphaned_engagements
    redis_settings = _redis_settings()
    # Pipelines can take many minutes (LLM calls, dep installs in Docker,
    # diff-execute) so push the job timeout out from the default 5 min.
    job_timeout = 60 * 30
    max_jobs = 4
    keep_result = 60 * 60
    # Heartbeat Redis key + interval. The API's /health/worker endpoint
    # reads this key to detect a dead worker. TTL is interval+1s so a
    # missed beat shows up within a single check window.
    health_check_key = HEALTH_CHECK_KEY
    health_check_interval = 30
    cron_jobs = [
        cron(reset_monthly_budgets, hour=0, minute=5),
        cron(refresh_trivy_db, hour=3, minute=0),
    ]
