from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from redis import asyncio as aioredis

from app.config import settings

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

    async def handle(self, engagement_id: str, websocket: WebSocket) -> None:
        """Accept and service a single client connection until it disconnects.

        Spawns a Redis subscriber task for the duration of the connection;
        every message published to `engagement:{id}` is forwarded to this
        socket. Also implements a basic keepalive ping/pong.
        """
        await self.connect(engagement_id, websocket)
        forwarder = asyncio.create_task(self._forward_redis(engagement_id, websocket))
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
            pass
        finally:
            forwarder.cancel()
            try:
                await forwarder
            except (asyncio.CancelledError, Exception):
                pass
            self.disconnect(engagement_id, websocket)

    async def _forward_redis(self, engagement_id: str, websocket: WebSocket) -> None:
        """Subscribe to engagement:{id} and forward each message to the socket."""
        try:
            client = aioredis.from_url(settings.redis_url, decode_responses=True)
        except Exception:
            logger.exception("redis subscribe failed for %s — live events will not stream", engagement_id)
            return
        pubsub = client.pubsub()
        try:
            await pubsub.subscribe(f"engagement:{engagement_id}")
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                try:
                    payload = json.loads(msg["data"])
                except Exception:
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
