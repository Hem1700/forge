# backend/tests/test_agent_brain.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.brain.agent_brain import AgentBrain, AgentBrainResult
from app.brain.agent_tools import AgentTool


class _EchoTool(AgentTool):
    """Test-only tool that echoes its args."""
    name = "echo"
    description = "Echoes args back."

    async def execute(self, args: dict) -> str:
        return f"echo: {args}"


def _llm_resp(content: str) -> MagicMock:
    m = MagicMock()
    m.content = content
    return m


@pytest.mark.asyncio
async def test_agent_brain_stops_at_conclusion():
    brain = AgentBrain(system_prompt="Test agent.", tools=[_EchoTool()])
    conclusion = json.dumps({
        "conclusion": True,
        "confidence": 0.92,
        "findings": [{"vulnerability_class": "sqli", "severity": "high", "evidence": "SQL error", "description": "SQLi found"}],
        "reasoning": "Confirmed",
    })
    brain._llm.ainvoke = AsyncMock(return_value=_llm_resp(conclusion))

    result = await brain.run({"attack_class": "sqli"}, {"target_url": "https://t.com"})

    assert isinstance(result, AgentBrainResult)
    assert result.confidence == 0.92
    assert result.steps_taken == 1
    assert len(result.findings) == 1
    assert result.findings[0]["vulnerability_class"] == "sqli"


@pytest.mark.asyncio
async def test_agent_brain_executes_tool_then_concludes():
    brain = AgentBrain(system_prompt="Test agent.", tools=[_EchoTool()])
    tool_call = json.dumps({"tool": "echo", "args": {"msg": "test"}, "reasoning": "testing", "confidence": 0.4})
    conclusion = json.dumps({"conclusion": True, "confidence": 0.9, "findings": [], "reasoning": "done"})
    brain._llm.ainvoke = AsyncMock(side_effect=[_llm_resp(tool_call), _llm_resp(conclusion)])

    result = await brain.run({}, {})

    assert result.steps_taken == 2
    assert result.confidence == 0.9
    assert brain._llm.ainvoke.call_count == 2


@pytest.mark.asyncio
async def test_agent_brain_stops_at_max_steps():
    brain = AgentBrain(system_prompt="Test agent.", tools=[_EchoTool()], max_steps=3)
    # Always returns a tool call, never concludes
    tool_call = json.dumps({"tool": "echo", "args": {}, "reasoning": "keep going", "confidence": 0.3})
    brain._llm.ainvoke = AsyncMock(return_value=_llm_resp(tool_call))

    result = await brain.run({}, {})

    assert result.steps_taken == 3
    assert result.confidence == 0.0
    assert result.findings == []
    assert brain._llm.ainvoke.call_count == 3


@pytest.mark.asyncio
async def test_agent_brain_stops_when_tool_call_confidence_hits_threshold():
    brain = AgentBrain(system_prompt="Test agent.", tools=[_EchoTool()], confidence_threshold=0.85)
    # Tool call with confidence above threshold
    high_conf = json.dumps({"tool": "echo", "args": {}, "reasoning": "high confidence", "confidence": 0.90})
    brain._llm.ainvoke = AsyncMock(return_value=_llm_resp(high_conf))

    result = await brain.run({}, {})

    assert result.confidence == 0.90
    assert result.steps_taken == 1
    # Loop stopped without calling LLM again
    assert brain._llm.ainvoke.call_count == 1


@pytest.mark.asyncio
async def test_agent_brain_handles_unknown_tool_gracefully():
    brain = AgentBrain(system_prompt="Test agent.", tools=[_EchoTool()])
    bad_call = json.dumps({"tool": "nonexistent", "args": {}, "reasoning": "oops", "confidence": 0.3})
    conclusion = json.dumps({"conclusion": True, "confidence": 0.5, "findings": [], "reasoning": "gave up"})
    brain._llm.ainvoke = AsyncMock(side_effect=[_llm_resp(bad_call), _llm_resp(conclusion)])

    result = await brain.run({}, {})

    # Should not crash — error message passed back as tool result
    assert result.steps_taken == 2


@pytest.mark.asyncio
async def test_agent_brain_handles_malformed_llm_json():
    brain = AgentBrain(system_prompt="Test agent.", tools=[_EchoTool()])
    brain._llm.ainvoke = AsyncMock(return_value=_llm_resp("not valid json {{ }}"))

    result = await brain.run({}, {})

    assert result.findings == []
    assert result.confidence == 0.0
    assert result.steps_taken == 1


@pytest.mark.asyncio
async def test_agent_brain_strips_markdown_fences_from_llm_response():
    brain = AgentBrain(system_prompt="Test agent.", tools=[_EchoTool()])
    conclusion = json.dumps({"conclusion": True, "confidence": 0.88, "findings": [], "reasoning": "ok"})
    brain._llm.ainvoke = AsyncMock(return_value=_llm_resp(f"```json\n{conclusion}\n```"))

    result = await brain.run({}, {})

    assert result.confidence == 0.88
