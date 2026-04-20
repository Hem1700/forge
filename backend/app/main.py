from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from app.api import engagements, findings, gates, knowledge, system
from app.api.start import router as start_router
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.engagement import Engagement, EngagementStatus
from app.ws.stream import stream_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Mark stale running/paused engagements as aborted on startup — any process
    # that was running them is long gone if the row was created >1h ago.
    cutoff = datetime.utcnow() - timedelta(hours=1)
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Engagement)
                .where(
                    Engagement.status.in_([EngagementStatus.running, EngagementStatus.paused_at_gate]),
                    Engagement.created_at < cutoff,
                )
                .values(status=EngagementStatus.aborted)
            )
            await db.commit()
    except Exception:
        pass
    yield


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


app.include_router(engagements.router)
app.include_router(findings.router)
app.include_router(gates.router)
app.include_router(knowledge.router)
app.include_router(system.router)
app.include_router(start_router)


@app.websocket("/ws/{engagement_id}")
async def websocket_endpoint(engagement_id: str, websocket: WebSocket):
    await stream_manager.handle(engagement_id, websocket)
