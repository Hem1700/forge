from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect


class SwarmStreamManager:
    """Fan-out manager for per-engagement WebSocket subscribers.

    Each engagement may have zero or more connected clients. `broadcast`
    delivers a single event dict to every live socket for that engagement
    and silently prunes connections that error out on send.
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

        Implements a basic keepalive: if no message arrives within 30s the
        server sends a `ping` prompt, and replies `pong` to any `ping` the
        client sends.
        """
        await self.connect(engagement_id, websocket)
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
            self.disconnect(engagement_id, websocket)


stream_manager = SwarmStreamManager()
