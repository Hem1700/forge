"""Shared event broadcaster — persist to DB, fan out to WebSocket subscribers.

Lives here (not in start.py) so brain components and swarm agents can import
it without a circular dependency on the start-endpoint module.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.database import AsyncSessionLocal
from app.models.engagement_event import EngagementEvent
from app.ws.stream import stream_manager


async def broadcast(engagement_id: str, event_type: str, payload: dict) -> None:
    """Persist an event then broadcast it to all WebSocket subscribers."""
    ts = datetime.now(timezone.utc)
    try:
        async with AsyncSessionLocal() as db:
            db.add(EngagementEvent(
                engagement_id=uuid.UUID(engagement_id),
                type=event_type,
                payload=payload,
                timestamp=ts.replace(tzinfo=None),
            ))
            await db.commit()
    except Exception:
        pass
    await stream_manager.broadcast(engagement_id, {
        "type": event_type,
        "payload": payload,
        "timestamp": ts.isoformat(),
    })


async def progress(engagement_id: str | None, phase: str, detail: str = "", **extra) -> None:
    """Emit a `progress` event. No-op if engagement_id is None (for unit tests)."""
    if not engagement_id:
        return
    await broadcast(engagement_id, "progress", {"phase": phase, "detail": detail, **extra})
