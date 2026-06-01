# backend/tests/test_agent_timeout.py
"""Tests for the per-agent timeout guard in the pipelines."""
import asyncio
import pytest
from app.api.start import _execute_with_timeout


class _SlowAgent:
    agent_type = "slow"
    engagement_id = "eng-1"

    async def _execute(self, task: dict) -> dict:
        await asyncio.sleep(10)
        return {"findings": [{"vulnerability": "found"}]}


class _FastAgent:
    agent_type = "fast"
    engagement_id = "eng-1"

    async def _execute(self, task: dict) -> dict:
        return {"agent_type": "fast", "findings": [{"vulnerability": "xss"}]}


class _RaisingAgent:
    agent_type = "boom"
    engagement_id = "eng-1"

    async def _execute(self, task: dict) -> dict:
        raise ValueError("kaboom")


@pytest.mark.asyncio
async def test_timeout_returns_empty_findings():
    agent = _SlowAgent()
    result = await _execute_with_timeout(agent, {}, timeout_seconds=0.05)
    assert result == {"agent_type": "slow", "findings": [], "timed_out": True}


@pytest.mark.asyncio
async def test_no_timeout_returns_findings():
    agent = _FastAgent()
    result = await _execute_with_timeout(agent, {}, timeout_seconds=5.0)
    assert result["findings"][0]["vulnerability"] == "xss"
    assert result.get("timed_out") is None


@pytest.mark.asyncio
async def test_non_timeout_exception_propagates():
    """Only TimeoutError is swallowed — other exceptions must propagate so the
    pipeline's gather(return_exceptions=True) handles them as before."""
    agent = _RaisingAgent()
    with pytest.raises(ValueError, match="kaboom"):
        await _execute_with_timeout(agent, {}, timeout_seconds=5.0)


@pytest.mark.asyncio
async def test_gather_isolates_slow_and_raising_agents():
    """One hung agent must not block or crash the fan-out: inside a
    gather(return_exceptions=True), a slow agent times out (empty + timed_out),
    a raising agent surfaces as an exception, and a fast agent is unaffected."""
    agents = [_SlowAgent(), _RaisingAgent(), _FastAgent()]
    results = await asyncio.gather(
        *[_execute_with_timeout(a, {}, timeout_seconds=0.05) for a in agents],
        return_exceptions=True,
    )
    assert results[0]["timed_out"] is True
    assert results[0]["findings"] == []
    assert isinstance(results[1], ValueError)
    assert results[2]["findings"][0]["vulnerability"] == "xss"
