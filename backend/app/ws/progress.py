"""Shared event broadcaster — persist to DB, fan out via Redis pub/sub.

Lives here (not in start.py) so brain components and swarm agents can import
it without a circular dependency on the start-endpoint module.

Events go to two places:
  1. Postgres (engagement_events) for refresh-safe replay.
  2. Redis pub/sub channel `engagement:{id}` so any API replica with a live
     WebSocket subscriber for this engagement can forward the message out.
     The worker process publishes; the API process subscribes per-connection.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from redis import asyncio as aioredis

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.engagement_event import EngagementEvent
from app.ws.stream import stream_manager

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


def channel_for(engagement_id: str) -> str:
    return f"engagement:{engagement_id}"


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def broadcast(engagement_id: str, event_type: str, payload: dict) -> None:
    """Persist an event then publish it to subscribers.

    Publishes with the DB row's autoincrement id so reconnecting clients
    can ask for `?since=<id>` and skip already-seen events.
    """
    ts = datetime.now(timezone.utc)
    event_id: int | None = None
    try:
        async with AsyncSessionLocal() as db:
            row = EngagementEvent(
                engagement_id=uuid.UUID(engagement_id),
                type=event_type,
                payload=payload,
                timestamp=ts.replace(tzinfo=None),
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            event_id = row.id
    except Exception:
        logger.exception("failed to persist event %s for %s", event_type, engagement_id)

    event = {
        "id": event_id,
        "type": event_type,
        "payload": payload,
        "timestamp": ts.isoformat(),
    }
    # Publish to Redis so any API replica with a subscribed WS client
    # forwards it. Falls back to in-process delivery if Redis is unavailable
    # so single-process dev still works without the worker.
    try:
        client = await _get_redis()
        await client.publish(channel_for(engagement_id), json.dumps(event))
    except Exception:
        logger.exception("redis publish failed for %s", engagement_id)
        await stream_manager.broadcast(engagement_id, event)


async def progress(engagement_id: str | None, phase: str, detail: str = "", **extra) -> None:
    """Emit a `progress` event. No-op if engagement_id is None (for unit tests)."""
    if not engagement_id:
        return
    await broadcast(engagement_id, "progress", {"phase": phase, "detail": detail, **extra})
