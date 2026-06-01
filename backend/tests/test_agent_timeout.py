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
