"""Tests for GET /api/v1/health/worker and worker startup recovery."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arq.jobs import JobStatus


@pytest.mark.asyncio
async def test_worker_health_up_returns_arq_stats(http_client):
    """Heartbeat key present → status=up + stats string forwarded as-is."""
    fake_pool = MagicMock()
    fake_pool.get = AsyncMock(
        return_value=b"j_complete=5 j_failed=0 j_retried=0 j_ongoing=2 queued=1"
    )
    with patch("app.main.get_pool", new=AsyncMock(return_value=fake_pool)):
        response = await http_client.get("/api/v1/health/worker")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "up"
    assert "j_complete=5" in body["stats"]
    assert "j_ongoing=2" in body["stats"]


@pytest.mark.asyncio
async def test_worker_health_down_when_key_missing(http_client):
    """No heartbeat key in Redis → status=down."""
    fake_pool = MagicMock()
    fake_pool.get = AsyncMock(return_value=None)
    with patch("app.main.get_pool", new=AsyncMock(return_value=fake_pool)):
        response = await http_client.get("/api/v1/health/worker")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "down"
    assert body["stats"] is None


@pytest.mark.asyncio
async def test_worker_health_unknown_when_redis_unreachable(http_client):
    """Redis errors should not 500 the endpoint — degrade to status=unknown."""
    with patch("app.main.get_pool", new=AsyncMock(side_effect=ConnectionError("redis down"))):
        response = await http_client.get("/api/v1/health/worker")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unknown"
    assert body["stats"] is None


@pytest.mark.asyncio
async def test_worker_health_decodes_string_value(http_client):
    """Some redis-py configs return str instead of bytes — handle both."""
    fake_pool = MagicMock()
    fake_pool.get = AsyncMock(return_value="j_complete=0 j_ongoing=0 queued=0")
    with patch("app.main.get_pool", new=AsyncMock(return_value=fake_pool)):
        response = await http_client.get("/api/v1/health/worker")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "up"
    assert body["stats"] == "j_complete=0 j_ongoing=0 queued=0"


# ── Worker startup recovery ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recover_orphaned_aborts_missing_job(db_session):
    """Running engagement whose job is not_found in Redis is aborted on worker startup."""
    from app.worker import _recover_orphaned_engagements
    from app.models.engagement import Engagement, EngagementStatus
    from app.models.organization import Organization

    org = Organization(name=f"test-org-{uuid.uuid4()}")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    eng = Engagement(
        org_id=org.id,
        target_url="https://example.com",
        target_type="web",
        status=EngagementStatus.running,
        started_at=datetime.utcnow() - timedelta(minutes=5),
        job_id="orphaned-job-id",
    )
    db_session.add(eng)
    await db_session.commit()
    await db_session.refresh(eng)

    with patch("app.worker.job_status", new=AsyncMock(return_value=JobStatus.not_found)), \
         patch("app.worker.AsyncSessionLocal") as mock_session_cls, \
         patch("app.worker.ws_progress.broadcast", new=AsyncMock()):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        await _recover_orphaned_engagements({})

    await db_session.refresh(eng)
    assert eng.status == EngagementStatus.aborted


@pytest.mark.asyncio
async def test_recover_orphaned_leaves_active_job_running(db_session):
    """Running engagement whose Arq job is still active must NOT be aborted."""
    from app.worker import _recover_orphaned_engagements
    from app.models.engagement import Engagement, EngagementStatus
    from app.models.organization import Organization

    org = Organization(name=f"test-org-{uuid.uuid4()}")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    eng = Engagement(
        org_id=org.id,
        target_url="https://active.example.com",
        target_type="web",
        status=EngagementStatus.running,
        started_at=datetime.utcnow() - timedelta(minutes=5),
        job_id="active-job-id",
    )
    db_session.add(eng)
    await db_session.commit()
    await db_session.refresh(eng)

    with patch("app.worker.job_status", new=AsyncMock(return_value=JobStatus.in_progress)), \
         patch("app.worker.AsyncSessionLocal") as mock_session_cls, \
         patch("app.worker.ws_progress.broadcast", new=AsyncMock()):
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=db_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        await _recover_orphaned_engagements({})

    await db_session.refresh(eng)
    assert eng.status == EngagementStatus.running
