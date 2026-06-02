# backend/tests/test_latency_stats_endpoint.py
"""API tests for GET /api/v1/org/llm/latency-stats."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.user import User, UserRole
from app.models.organization import Organization
from app.models.llm_usage import LLMUsageEvent
from app.api.deps import get_current_user

TEST_DB = "postgresql+asyncpg://forge:forge@localhost:5432/forge_test"
_pwd = CryptContext(schemes=["sha256_crypt"], deprecated="auto")


@pytest_asyncio.fixture
async def seeded_client():
    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        org = Organization(name=f"test-org-{uuid.uuid4()}")
        db.add(org)
        await db.commit()
        await db.refresh(org)

        user = User(
            email=f"admin-{uuid.uuid4()}@test.forge",
            hashed_password=_pwd.hash("testpass"),
            role=UserRole.super_admin,
            org_id=org.id,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        now = datetime.utcnow()
        old = now - timedelta(days=30)
        # campaign_planning: durations 100,200,300 (recent)
        for dur, itok, otok in [(100, 200, 20), (200, 400, 40), (300, 600, 60)]:
            db.add(LLMUsageEvent(
                org_id=org.id, task="campaign_planning", provider="anthropic",
                model="claude-sonnet-4-6", input_tokens=itok, output_tokens=otok,
                cost_usd=0, duration_ms=dur, created_at=now,
            ))
        # code_analyzer: one recent
        db.add(LLMUsageEvent(
            org_id=org.id, task="code_analyzer", provider="anthropic",
            model="claude-sonnet-4-6", input_tokens=100, output_tokens=10,
            cost_usd=0, duration_ms=50, created_at=now,
        ))
        # an OLD campaign_planning row to test the since filter
        db.add(LLMUsageEvent(
            org_id=org.id, task="campaign_planning", provider="anthropic",
            model="claude-sonnet-4-6", input_tokens=999, output_tokens=999,
            cost_usd=0, duration_ms=9999, created_at=old,
        ))
        await db.commit()

    async def override_db():
        async with session_factory() as session:
            yield session

    async def override_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.mark.asyncio
async def test_latency_stats_returns_per_task(seeded_client):
    resp = await seeded_client.get("/api/v1/org/llm/latency-stats")
    assert resp.status_code == 200
    data = resp.json()
    tasks = {t["task"]: t for t in data["tasks"]}
    assert "campaign_planning" in tasks
    assert "code_analyzer" in tasks

    cp = tasks["campaign_planning"]
    # includes the OLD row too (no since filter): durations [100,200,300,9999]
    assert cp["calls"] == 4
    assert cp["latency_ms"]["max"] == 9999

    ca = tasks["code_analyzer"]
    assert ca["calls"] == 1
    assert ca["latency_ms"]["avg"] == 50.0


@pytest.mark.asyncio
async def test_latency_stats_since_filter_excludes_old(seeded_client):
    cutoff = (datetime.utcnow() - timedelta(days=1)).isoformat()
    resp = await seeded_client.get(f"/api/v1/org/llm/latency-stats?since={cutoff}")
    assert resp.status_code == 200
    data = resp.json()
    tasks = {t["task"]: t for t in data["tasks"]}
    # old 9999ms campaign_planning row excluded -> only 3 recent
    cp = tasks["campaign_planning"]
    assert cp["calls"] == 3
    assert cp["latency_ms"]["max"] == 300
    assert cp["latency_ms"]["p50"] == 200.0


@pytest.mark.asyncio
async def test_latency_stats_bad_since_returns_400(seeded_client):
    resp = await seeded_client.get("/api/v1/org/llm/latency-stats?since=not-a-date")
    assert resp.status_code == 400
