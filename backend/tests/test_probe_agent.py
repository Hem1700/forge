# backend/tests/test_probe_agent.py
import pytest
from unittest.mock import AsyncMock
from app.swarm.agents.probe import ProbeAgent
from app.brain.agent_brain import AgentBrainResult


def _make_agent():
    return ProbeAgent(
        agent_id="probe-1",
        engagement_id="eng-1",
        agent_type="probe",
        tools=["http_request"],
    )


@pytest.mark.asyncio
async def test_probe_agent_execute_delegates_to_brain():
    agent = _make_agent()
    mock_result = AgentBrainResult(
        findings=[{"vulnerability_class": "sqli", "severity": "high", "evidence": "SQL error", "description": "SQLi confirmed"}],
        confidence=0.91,
        steps_taken=5,
    )
    agent.brain.run = AsyncMock(return_value=mock_result)

    result = await agent._execute({"surface": "https://target.com", "attack_class": "sqli"})

    assert result["agent_type"] == "probe"
    assert result["attack_class"] == "sqli"
    assert len(result["findings"]) == 1
    assert result["confidence"] == 0.91
    agent.brain.run.assert_called_once()


@pytest.mark.asyncio
async def test_probe_agent_passes_hypothesis_and_context():
    agent = _make_agent()
    agent.brain.run = AsyncMock(
        return_value=AgentBrainResult(findings=[], confidence=0.3, steps_taken=2)
    )

    task = {
        "surface": "https://api.com",
        "attack_class": "idor",
        "hypothesis": {"attack_class": "idor", "parameter": "user_id"},
        "context": {"target_url": "https://api.com", "app_type": "api"},
    }
    await agent._execute(task)

    call_args = agent.brain.run.call_args[0]
    assert call_args[0] == task["hypothesis"]
    assert call_args[1] == task["context"]


@pytest.mark.asyncio
async def test_probe_agent_bid_higher_for_known_attack_class():
    agent = _make_agent()
    bid_known = await agent.bid({"attack_class": "sqli", "surface": "https://t.com"})
    assert bid_known["confidence"] == 0.75

    bid_unknown = await agent.bid({"attack_class": "unknown_technique", "surface": "https://t.com"})
    assert bid_unknown["confidence"] == 0.55
