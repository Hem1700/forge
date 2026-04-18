# backend/tests/test_recon_agent.py
import pytest
from unittest.mock import AsyncMock
from app.swarm.agents.recon import ReconAgent
from app.brain.agent_brain import AgentBrainResult


def _make_agent():
    return ReconAgent(
        agent_id="recon-1",
        engagement_id="eng-1",
        agent_type="recon",
        tools=["http_request"],
    )


@pytest.mark.asyncio
async def test_recon_agent_execute_delegates_to_brain():
    agent = _make_agent()
    mock_result = AgentBrainResult(
        findings=[{"vulnerability_class": "info", "severity": "low", "evidence": "/admin found", "description": "Admin path exposed"}],
        confidence=0.88,
        steps_taken=3,
    )
    agent.brain.run = AsyncMock(return_value=mock_result)

    result = await agent._execute({"surface": "https://target.com"})

    assert result["agent_type"] == "recon"
    assert result["surface"] == "https://target.com"
    assert len(result["findings"]) == 1
    assert result["confidence"] == 0.88
    agent.brain.run.assert_called_once()


@pytest.mark.asyncio
async def test_recon_agent_passes_hypothesis_and_context_when_provided():
    agent = _make_agent()
    agent.brain.run = AsyncMock(
        return_value=AgentBrainResult(findings=[], confidence=0.5, steps_taken=1)
    )

    task = {
        "surface": "https://app.com",
        "hypothesis": {"attack_class": "recon", "title": "Discover endpoints"},
        "context": {"target_url": "https://app.com", "app_type": "api"},
    }
    await agent._execute(task)

    call_args = agent.brain.run.call_args[0]
    assert call_args[0] == task["hypothesis"]
    assert call_args[1] == task["context"]


@pytest.mark.asyncio
async def test_recon_agent_falls_back_to_surface_when_no_context():
    agent = _make_agent()
    agent.brain.run = AsyncMock(
        return_value=AgentBrainResult(findings=[], confidence=0.3, steps_taken=1)
    )

    await agent._execute({"surface": "https://fallback.com"})

    call_args = agent.brain.run.call_args[0]
    # context should include target_url from surface
    assert call_args[1].get("target_url") == "https://fallback.com"


@pytest.mark.asyncio
async def test_recon_agent_bid_higher_for_recon_keywords():
    agent = _make_agent()
    bid = await agent.bid({"title": "endpoint discovery and recon scan", "surface": "https://t.com"})
    assert bid["confidence"] > 0.5
    assert bid["agent_id"] == "recon-1"
