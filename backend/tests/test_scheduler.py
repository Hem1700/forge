import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
from app.swarm.scheduler import SwarmScheduler
from app.swarm.agents.probe import ProbeAgent
from app.swarm.agents.recon import ReconAgent


@pytest.fixture
def scheduler():
    return SwarmScheduler(engagement_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_scheduler_registers_agent(scheduler):
    agent = ReconAgent(agent_id=str(uuid.uuid4()), engagement_id=scheduler.engagement_id, agent_type="recon", tools=[])
    scheduler.register_agent(agent)
    assert agent.agent_id in scheduler.agents


@pytest.mark.asyncio
async def test_run_auction_assigns_highest_bidder(scheduler):
    task = {"task_id": str(uuid.uuid4()), "title": "Subdomain enumeration", "surface": "example.com", "required_confidence": 0.5, "priority": "high", "attack_class": "recon"}
    agent_low = ProbeAgent(agent_id="agent-low", engagement_id=scheduler.engagement_id, agent_type="probe", tools=[])
    agent_high = ReconAgent(agent_id="agent-high", engagement_id=scheduler.engagement_id, agent_type="recon", tools=[])
    scheduler.register_agent(agent_low)
    scheduler.register_agent(agent_high)
    winner = await scheduler.run_auction(task)
    assert winner is not None
    assert winner.agent_id == "agent-high"


@pytest.mark.asyncio
async def test_scheduler_tracks_lineage(scheduler):
    parent = ReconAgent(agent_id="parent-1", engagement_id=scheduler.engagement_id, agent_type="recon", tools=[])
    scheduler.register_agent(parent)
    child = parent.spawn_child("found something interesting")
    scheduler.register_agent(child)
    lineage = scheduler.get_lineage("parent-1")
    assert child.agent_id in lineage
