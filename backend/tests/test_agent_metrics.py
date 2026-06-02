# backend/tests/test_agent_metrics.py
"""Tests that agent rows carry timing data."""
import uuid
import pytest
from datetime import datetime, timezone
from app.models.agent import Agent, AgentType, AgentStatus


def test_agent_model_has_timing_columns():
    """Agent model must accept started_at, completed_at, duration_ms."""
    now = datetime.now(timezone.utc)
    agent = Agent(
        engagement_id=uuid.uuid4(),
        type=AgentType.recon,
        spawned_reason="test",
        status=AgentStatus.completed,
        tools=[],
        started_at=now,
        completed_at=now,
        duration_ms=1234,
    )
    assert agent.duration_ms == 1234
    assert agent.started_at is not None
    assert agent.completed_at is not None


@pytest.mark.asyncio
async def test_stamp_agent_duration_issues_update():
    """_stamp_agent_duration() issues an UPDATE setting started_at, completed_at,
    a non-negative duration_ms, and status=completed."""
    from unittest.mock import AsyncMock
    from app.api.start import _stamp_agent_duration
    from app.models.agent import AgentStatus

    mock_db = AsyncMock()
    agent_id = uuid.uuid4()
    started = datetime.now(timezone.utc)
    await _stamp_agent_duration(mock_db, agent_id, started)

    mock_db.execute.assert_awaited_once()
    stmt = mock_db.execute.call_args.args[0]
    params = stmt.compile().params
    assert params["duration_ms"] >= 0
    assert params["status"] == AgentStatus.completed
    assert params["started_at"] == started
