# backend/tests/test_agents.py
import pytest
import uuid
from unittest.mock import AsyncMock, patch
from app.swarm.agents.base import BaseAgent, AgentState


def make_agent(agent_type="probe"):
    return BaseAgent(
        agent_id=str(uuid.uuid4()),
        engagement_id=str(uuid.uuid4()),
        agent_type=agent_type,
        tools=[],
    )


def test_agent_initial_state():
    agent = make_agent()
    assert agent.state == AgentState.IDLE
    assert agent.signal_history == []
    assert agent.parent_id is None


def test_agent_emit_signal_tracks_history():
    agent = make_agent()
    agent.emit_signal(0.9)
    agent.emit_signal(0.1)
    agent.emit_signal(0.2)
    assert len(agent.signal_history) == 3
    assert agent.signal_history[0] == 0.9


def test_agent_is_dead_when_signals_too_low():
    agent = make_agent()
    for _ in range(5):
        agent.emit_signal(0.1)
    assert agent.is_dead() is True


def test_agent_not_dead_with_mixed_signals():
    agent = make_agent()
    for _ in range(4):
        agent.emit_signal(0.1)
    agent.emit_signal(0.9)
    assert agent.is_dead() is False


def test_agent_rolling_average():
    agent = make_agent()
    for _ in range(10):
        agent.emit_signal(0.1)
    agent.emit_signal(0.9)
    # rolling window is last 5 — [0.1, 0.1, 0.1, 0.1, 0.9] avg = 0.26
    assert agent.rolling_signal_average() > 0.2


@pytest.mark.asyncio
async def test_agent_bid_returns_bid_dict():
    agent = make_agent()
    task = {
        "task_id": str(uuid.uuid4()),
        "title": "Test JWT bypass",
        "surface": "/api/auth",
        "required_confidence": 0.7,
        "priority": "high",
    }
    bid = await agent.bid(task)
    assert "confidence" in bid
    assert "basis" in bid
    assert "noise_level" in bid
    assert 0.0 <= bid["confidence"] <= 1.0


from app.swarm.agents.recon import ReconAgent
from app.swarm.agents.child import ChildAgent


@pytest.mark.asyncio
async def test_recon_agent_bids_high_on_recon_tasks():
    agent = ReconAgent(
        agent_id=str(uuid.uuid4()),
        engagement_id=str(uuid.uuid4()),
        agent_type="recon",
        tools=["httpx", "subfinder"],
    )
    task = {"task_id": str(uuid.uuid4()), "title": "Subdomain enumeration", "surface": "example.com", "required_confidence": 0.5, "priority": "high"}
    bid = await agent.bid(task)
    assert bid["confidence"] >= 0.7


@pytest.mark.asyncio
async def test_child_agent_inherits_parent():
    parent = ReconAgent(
        agent_id="parent-001",
        engagement_id=str(uuid.uuid4()),
        agent_type="recon",
        tools=["httpx"],
    )
    child = parent.spawn_child(reason="Found JS bundle, needs analysis", tools=["js_analyzer"])
    assert child.parent_id == "parent-001"
    assert child.spawned_reason == "Found JS bundle, needs analysis"
    assert "js_analyzer" in child.tools
