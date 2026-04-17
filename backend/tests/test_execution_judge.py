# backend/tests/test_execution_judge.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.brain.execution_judge import ExecutionJudge

MOCK_VERDICT_CONFIRMED = {
    "verdict": "confirmed",
    "confidence": 0.94,
    "reasoning": "Script successfully dumped 47 user records including hashed passwords. Output contains bcrypt hashes consistent with a user credential table.",
}

MOCK_VERDICT_FAILED = {
    "verdict": "failed",
    "confidence": 0.92,
    "reasoning": "Script returned HTTP 403 Forbidden. The target has likely been patched or the payload was blocked by a WAF.",
}

MOCK_VERDICT_INCONCLUSIVE = {
    "verdict": "inconclusive",
    "confidence": 0.55,
    "reasoning": "Script returned a 200 response but output contains only a generic success message — cannot confirm data extraction.",
}


@pytest.mark.asyncio
async def test_execution_judge_confirmed():
    judge = ExecutionJudge()
    mock_response = MagicMock()
    mock_response.content = json.dumps(MOCK_VERDICT_CONFIRMED)
    judge._llm.ainvoke = AsyncMock(return_value=mock_response)

    finding = {"vulnerability_class": "sqli", "severity": "high", "affected_surface": "/api/users", "description": "SQLi"}
    result = await judge.judge(
        finding=finding,
        script="import requests\n...",
        stdout="id|username|password\n1|admin|$2b$12$abc...\n2|user|$2b$12$def...",
        stderr="",
        exit_code=0,
    )

    assert result["verdict"] == "confirmed"
    assert result["confidence"] == 0.94
    assert "reasoning" in result


@pytest.mark.asyncio
async def test_execution_judge_failed():
    judge = ExecutionJudge()
    mock_response = MagicMock()
    mock_response.content = json.dumps(MOCK_VERDICT_FAILED)
    judge._llm.ainvoke = AsyncMock(return_value=mock_response)

    finding = {"vulnerability_class": "sqli", "severity": "high", "affected_surface": "/api/users", "description": "SQLi"}
    result = await judge.judge(
        finding=finding,
        script="import requests\n...",
        stdout="",
        stderr="403 Forbidden",
        exit_code=1,
    )

    assert result["verdict"] == "failed"
    assert result["confidence"] > 0.5


@pytest.mark.asyncio
async def test_execution_judge_passes_all_context_to_llm():
    judge = ExecutionJudge()
    mock_response = MagicMock()
    mock_response.content = json.dumps(MOCK_VERDICT_CONFIRMED)
    judge._llm.ainvoke = AsyncMock(return_value=mock_response)

    finding = {"vulnerability_class": "cmdi", "severity": "critical", "affected_surface": "/exec", "description": "RCE"}
    await judge.judge(
        finding=finding,
        script="bash -c 'id'",
        stdout="uid=0(root) gid=0(root)",
        stderr="",
        exit_code=0,
    )

    call_args = judge._llm.ainvoke.call_args[0][0]
    human_message = call_args[1]
    assert "cmdi" in human_message.content
    assert "uid=0(root)" in human_message.content
    assert "exit_code=0" in human_message.content


@pytest.mark.asyncio
async def test_execution_judge_raises_on_invalid_json():
    judge = ExecutionJudge()
    mock_response = MagicMock()
    mock_response.content = "this is not json"
    judge._llm.ainvoke = AsyncMock(return_value=mock_response)

    finding = {"vulnerability_class": "sqli", "severity": "high", "affected_surface": "/api", "description": "SQLi"}
    with pytest.raises(ValueError, match="ExecutionJudge"):
        await judge.judge(finding=finding, script="...", stdout="", stderr="", exit_code=1)
