"""Tests for the worker-crash recovery sweep in app.main._sweep_orphaned_engagements."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from arq.jobs import JobStatus

from app.main import _sweep_orphaned_engagements
from app.models.engagement import Engagement, EngagementStatus


def _shared_session_factory(session):
    """Patch target for `AsyncSessionLocal` — yields the test fixture session
    without closing it so the test's later `refresh(...)` calls still work.
    """
    @asynccontextmanager
    async def _cm():
        yield session
    return lambda: _cm()


@pytest.mark.asyncio
async def test_sweep_aborts_engagement_when_arq_job_is_gone(db_session):
    """`running` + job_id whose Arq status is `not_found` → aborted."""
    eng = Engagement(
        id=uuid.uuid4(),
        target_url="https://example.com",
        target_type="web",
        status=EngagementStatus.running,
        started_at=datetime.utcnow() - timedelta(minutes=5),
        job_id="job_that_isnt_in_redis",
    )
    db_session.add(eng)
    await db_session.commit()

    with patch("app.main.AsyncSessionLocal", _shared_session_factory(db_session)), \
         patch("app.main.job_status", new=AsyncMock(return_value=JobStatus.not_found)), \
         patch("app.main.ws_progress.broadcast", new=AsyncMock(return_value=None)) as bcast:
        await _sweep_orphaned_engagements()

    await db_session.refresh(eng)
    assert eng.status == EngagementStatus.aborted
    bcast.assert_awaited_once()
    args, _ = bcast.call_args
    assert args[0] == str(eng.id)
    assert args[1] == "engagement_aborted"
    assert "worker crashed" in args[2]["reason"]


@pytest.mark.asyncio
async def test_sweep_leaves_alive_engagement_alone(db_session):
    """`running` + job_id whose Arq status is in_progress → untouched."""
    eng = Engagement(
        id=uuid.uuid4(),
        target_url="https://example.com",
        target_type="web",
        status=EngagementStatus.running,
        started_at=datetime.utcnow() - timedelta(minutes=2),
        job_id="job_thats_running",
    )
    db_session.add(eng)
    await db_session.commit()

    with patch("app.main.AsyncSessionLocal", _shared_session_factory(db_session)), \
         patch("app.main.job_status", new=AsyncMock(return_value=JobStatus.in_progress)), \
         patch("app.main.ws_progress.broadcast", new=AsyncMock(return_value=None)) as bcast:
        await _sweep_orphaned_engagements()

    await db_session.refresh(eng)
    assert eng.status == EngagementStatus.running
    bcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_sweep_legacy_running_no_job_id_after_cutoff_is_aborted(db_session):
    """No job_id (pre-Arq data) and started_at older than 1h → aborted via fallback."""
    eng = Engagement(
        id=uuid.uuid4(),
        target_url="https://example.com",
        target_type="web",
        status=EngagementStatus.running,
        started_at=datetime.utcnow() - timedelta(hours=2),
        job_id=None,
    )
    db_session.add(eng)
    await db_session.commit()

    with patch("app.main.AsyncSessionLocal", _shared_session_factory(db_session)), \
         patch("app.main.job_status", new=AsyncMock()) as job_status_mock, \
         patch("app.main.ws_progress.broadcast", new=AsyncMock(return_value=None)):
        await _sweep_orphaned_engagements()

    job_status_mock.assert_not_awaited()  # no job_id → never queried Arq
    await db_session.refresh(eng)
    assert eng.status == EngagementStatus.aborted


@pytest.mark.asyncio
async def test_sweep_legacy_running_no_job_id_recent_is_kept(db_session):
    """No job_id but started_at within the cutoff → still running."""
    eng = Engagement(
        id=uuid.uuid4(),
        target_url="https://example.com",
        target_type="web",
        status=EngagementStatus.running,
        started_at=datetime.utcnow() - timedelta(minutes=10),
        job_id=None,
    )
    db_session.add(eng)
    await db_session.commit()

    with patch("app.main.AsyncSessionLocal", _shared_session_factory(db_session)), \
         patch("app.main.job_status", new=AsyncMock()), \
         patch("app.main.ws_progress.broadcast", new=AsyncMock(return_value=None)):
        await _sweep_orphaned_engagements()

    await db_session.refresh(eng)
    assert eng.status == EngagementStatus.running


@pytest.mark.asyncio
async def test_sweep_paused_at_gate_stale_is_aborted(db_session):
    """Paused engagement older than 1h still gets coarse-swept (preserved behavior)."""
    eng = Engagement(
        id=uuid.uuid4(),
        target_url="https://example.com",
        target_type="web",
        status=EngagementStatus.paused_at_gate,
        started_at=datetime.utcnow() - timedelta(hours=3),
    )
    db_session.add(eng)
    await db_session.commit()

    with patch("app.main.AsyncSessionLocal", _shared_session_factory(db_session)), \
         patch("app.main.job_status", new=AsyncMock()), \
         patch("app.main.ws_progress.broadcast", new=AsyncMock(return_value=None)):
        await _sweep_orphaned_engagements()

    await db_session.refresh(eng)
    assert eng.status == EngagementStatus.aborted
