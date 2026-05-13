import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from arq.jobs import JobStatus
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, update

from app.api import api_keys, auth, engagements, findings, gates, knowledge, system
from app.api.start import router as start_router
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.engagement import Engagement, EngagementStatus
from app.queue import close_pool, get_pool, job_status
from app.worker import HEALTH_CHECK_KEY
from app.ws import progress as ws_progress
from app.ws.stream import stream_manager

logger = logging.getLogger(__name__)


async def _sweep_orphaned_engagements() -> None:
    """Recover from worker crashes by aborting engagements whose job is gone.

    Two paths:
    1. `running` engagements with a `job_id`: ask Arq for the job status.
       If `not_found`, the worker died (or result was evicted) — abort now,
       don't wait for the time-based fallback.
    2. `running` engagements without a `job_id` (legacy data) and any
       `paused_at_gate` engagement that's been quiet too long: abort if
       `started_at` is older than 1h. Same coarse heuristic as before.

    Aborts publish an `engagement_aborted` event so the UI updates the next
    time a client connects (event is also persisted to engagement_events).
    """
    cutoff = datetime.utcnow() - timedelta(hours=1)
    aborted: list[tuple[str, str]] = []

    try:
        async with AsyncSessionLocal() as db:
            running = (
                await db.execute(
                    select(Engagement).where(Engagement.status == EngagementStatus.running)
                )
            ).scalars().all()

            for e in running:
                should_abort = False
                reason = ""
                if e.job_id:
                    try:
                        status = await job_status(e.job_id)
                    except Exception:
                        logger.exception("job_status lookup failed for %s", e.id)
                        continue
                    if status == JobStatus.not_found:
                        should_abort = True
                        reason = "worker crashed before completion"
                elif e.started_at and e.started_at < cutoff:
                    should_abort = True
                    reason = "stale running engagement with no recorded job"

                if should_abort:
                    e.status = EngagementStatus.aborted
                    aborted.append((str(e.id), reason))

            # Coarse fallback for paused-at-gate engagements that have been
            # idle too long; preserves prior startup-sweep behavior.
            await db.execute(
                update(Engagement)
                .where(
                    Engagement.status == EngagementStatus.paused_at_gate,
                    Engagement.started_at.is_not(None),
                    Engagement.started_at < cutoff,
                )
                .values(status=EngagementStatus.aborted)
            )
            await db.commit()
    except Exception:
        logger.exception("orphan sweep failed")
        return

    for eid, reason in aborted:
        try:
            await ws_progress.broadcast(eid, "engagement_aborted", {
                "engagement_id": eid,
                "reason": reason,
            })
        except Exception:
            logger.exception("failed to broadcast abort for %s", eid)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _sweep_orphaned_engagements()
    yield
    await close_pool()


app = FastAPI(
    title="FORGE",
    description="Framework for Offensive Reasoning, Generation and Exploitation",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:5175"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/v1/health/worker")
async def worker_health():
    """Return whether an Arq worker has recently written its heartbeat key.

    Arq workers psetex `HEALTH_CHECK_KEY` every `health_check_interval`
    seconds with TTL = interval + 1, so the key being absent means no
    worker has reported in within the last interval. `stats` is the raw
    Arq counter line (e.g. "j_complete=5 j_failed=0 j_ongoing=2 queued=1");
    callers can parse it if they need structured fields.
    """
    try:
        pool = await get_pool()
        raw = await pool.get(HEALTH_CHECK_KEY)
    except Exception:
        return {"status": "unknown", "stats": None}
    if raw is None:
        return {"status": "down", "stats": None}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    return {"status": "up", "stats": raw}


app.include_router(api_keys.router)
app.include_router(auth.router)
app.include_router(engagements.router)
app.include_router(findings.router)
app.include_router(gates.router)
app.include_router(knowledge.router)
app.include_router(system.router)
app.include_router(start_router)


@app.websocket("/ws/{engagement_id}")
async def websocket_endpoint(engagement_id: str, websocket: WebSocket):
    await stream_manager.handle(engagement_id, websocket)
