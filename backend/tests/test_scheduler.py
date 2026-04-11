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


from app.swarm.health_monitor import HealthMonitor
from app.swarm.agents.base import AgentState


@pytest.mark.asyncio
async def test_health_monitor_terminates_dead_agents():
    engagement_id = str(uuid.uuid4())
    agent = ProbeAgent(agent_id=str(uuid.uuid4()), engagement_id=engagement_id, agent_type="probe", tools=[])
    for _ in range(6):
        agent.emit_signal(0.05)
    scheduler = SwarmScheduler(engagement_id=engagement_id)
    scheduler.register_agent(agent)
    agent.state = AgentState.RUNNING
    monitor = HealthMonitor(scheduler)
    terminated = await monitor.check_and_purge()
    assert agent.agent_id in terminated
    assert agent.state == AgentState.TERMINATED


@pytest.mark.asyncio
async def test_health_monitor_keeps_healthy_agents():
    engagement_id = str(uuid.uuid4())
    agent = ReconAgent(agent_id=str(uuid.uuid4()), engagement_id=engagement_id, agent_type="recon", tools=[])
    agent.emit_signal(0.9)
    agent.emit_signal(0.8)
    agent.state = AgentState.RUNNING
    scheduler = SwarmScheduler(engagement_id=engagement_id)
    scheduler.register_agent(agent)
    monitor = HealthMonitor(scheduler)
    terminated = await monitor.check_and_purge()
    assert agent.agent_id not in terminated
    assert agent.state == AgentState.RUNNING
