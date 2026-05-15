from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from redis import asyncio as aioredis
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.engagement_event import EngagementEvent

logger = logging.getLogger(__name__)


class SwarmStreamManager:
    """Fan-out manager for per-engagement WebSocket subscribers.

    Each engagement may have zero or more connected clients in this process.
    Pipeline events are published to Redis (`engagement:{id}` channel) by
    whichever process runs the pipeline (worker or API). Each connected
    WebSocket spawns a Redis subscriber task that forwards messages to its
    socket — this is what lets the worker process broadcast events that
    reach clients connected to API replicas.

    `broadcast` is kept as an in-process fallback for single-process dev
    when Redis is unavailable; it delivers to local sockets only.
    """

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, engagement_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(engagement_id, set()).add(websocket)

    def disconnect(self, engagement_id: str, websocket: WebSocket) -> None:
        conns = self._connections.get(engagement_id, set())
        conns.discard(websocket)
        if not conns:
            self._connections.pop(engagement_id, None)

    async def broadcast(self, engagement_id: str, event: dict[str, Any]) -> None:
        dead: set[WebSocket] = set()
        for ws in list(self._connections.get(engagement_id, set())):
            try:
                await ws.send_json(event)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.disconnect(engagement_id, ws)

    async def handle(
        self,
        engagement_id: str,
        websocket: WebSocket,
        since: int | None = None,
    ) -> None:
        """Accept and service a single client connection until it disconnects.

        Flow:
        1. Accept the socket.
        2. If `since` is provided, replay every persisted event with id > since
           so reconnecting clients close the gap they missed.
        3. Subscribe to Redis pub/sub and forward live events.
        4. Keepalive pings every 30s.

        Either the forwarder or the keepalive completing causes the
        connection to be torn down — so a Redis failure tears down the
        socket cleanly and the client reconnects instead of staring at a
        silent zombie.
        """
        await self.connect(engagement_id, websocket)
        try:
            replayed_max = await self._replay_missed(engagement_id, websocket, since)

            forwarder = asyncio.create_task(
                self._forward_redis(engagement_id, websocket, skip_id_le=replayed_max)
            )
            keepalive = asyncio.create_task(self._keepalive(websocket))
            try:
                _, pending = await asyncio.wait(
                    {forwarder, keepalive},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                for task in pending:
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
            except WebSocketDisconnect:
                forwarder.cancel()
                keepalive.cancel()
        finally:
            self.disconnect(engagement_id, websocket)

    async def _replay_missed(
        self,
        engagement_id: str,
        websocket: WebSocket,
        since: int | None,
    ) -> int:
        """Send all persisted events with id > since. Returns max id sent (0 if none)."""
        if since is None:
            return 0
        try:
            engagement_uuid = uuid.UUID(engagement_id)
        except ValueError:
            return 0
        max_id = 0
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(EngagementEvent)
                    .where(
                        EngagementEvent.engagement_id == engagement_uuid,
                        EngagementEvent.id > since,
                    )
                    .order_by(EngagementEvent.id.asc())
                )
                for row in result.scalars().all():
                    await websocket.send_json({
                        "id": row.id,
                        "type": row.type,
                        "payload": row.payload,
                        "timestamp": row.timestamp.isoformat(),
                    })
                    if row.id > max_id:
                        max_id = row.id
        except Exception:
            logger.exception("replay failed for engagement %s", engagement_id)
        return max_id

    async def _keepalive(self, websocket: WebSocket) -> None:
        """Drive ping/pong on the socket; exit when the client disconnects."""
        try:
            while True:
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                except asyncio.TimeoutError:
                    await websocket.send_text("ping")
                    continue
                if data == "ping":
                    await websocket.send_text("pong")
        except WebSocketDisconnect:
            return

    async def _forward_redis(
        self,
        engagement_id: str,
        websocket: WebSocket,
        skip_id_le: int = 0,
    ) -> None:
        """Subscribe to engagement:{id} and forward each message to the socket.

        Drops live events with id <= `skip_id_le` to avoid double-delivery
        right after a replay. Notifies the client (stream_error) if Redis is
        unreachable and exits — so the connection tears down and the client
        knows to reconnect, instead of sitting on a silent socket.
        """
        try:
            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            pubsub = client.pubsub()
            await pubsub.subscribe(f"engagement:{engagement_id}")
        except Exception:
            logger.exception("redis subscribe failed for %s — notifying client", engagement_id)
            try:
                await websocket.send_json({
                    "id": None,
                    "type": "stream_error",
                    "payload": {"reason": "live events unavailable — reconnect to retry"},
                    "timestamp": "",
                })
            except Exception:
                pass
            return

        try:
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                try:
                    payload = json.loads(msg["data"])
                except Exception:
                    continue
                event_id = payload.get("id")
                if isinstance(event_id, int) and event_id <= skip_id_le:
                    continue
                try:
                    await websocket.send_json(payload)
                except Exception:
                    return
        finally:
            try:
                await pubsub.unsubscribe(f"engagement:{engagement_id}")
                await pubsub.aclose()
                await client.aclose()
            except Exception:
                pass


stream_manager = SwarmStreamManager()
