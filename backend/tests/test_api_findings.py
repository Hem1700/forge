import json
import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.models.finding import Finding, Severity, ValidationStatus
from app.models.engagement import Engagement, EngagementStatus, GateStatus
from app.models.agent import Agent, AgentType, AgentStatus
from app.models.task import Task, TaskStatus, Priority

MOCK_EXPLOIT = {
    "walkthrough": [{"step": 1, "title": "Test", "detail": "desc", "code": "curl http://x.com"}],
    "attack_path_mermaid": "graph LR\n  Attacker --> Server",
    "impact": "Data leak",
    "prerequisites": ["Network access"],
    "difficulty": "easy",
}


async def _create_engagement(db_session):
    eng = Engagement(
        target_url="https://example.com",
        target_type="web",
        status=EngagementStatus.complete,
        gate_status=GateStatus.complete,
        semantic_model={"app_type": "api"},
    )
    db_session.add(eng)
    await db_session.flush()
    return eng


async def _create_finding(db_session, engagement_id):
    agent = Agent(
        engagement_id=engagement_id,
        type=AgentType.recon,
        spawned_reason="test",
        status=AgentStatus.completed,
        tools=[],
    )
    db_session.add(agent)
    await db_session.flush()

    task = Task(
        engagement_id=engagement_id,
        title="test task",
        description="test",
        surface="web",
        priority=Priority.medium,
        status=TaskStatus.complete,
        created_by=agent.id,
    )
    db_session.add(task)
    await db_session.flush()

    finding = Finding(
        engagement_id=engagement_id,
        task_id=task.id,
        agent_id=agent.id,
        title="SQL Injection",
        description="Unsanitized id param",
        vulnerability_class="sqli",
        affected_surface="/api/users",
        evidence=["SELECT * FROM users WHERE id='1'"],
        severity=Severity.high,
        validation_status=ValidationStatus.pending,
        confidence_score=0.87,
    )
    db_session.add(finding)
    await db_session.commit()
    return finding


@pytest.mark.asyncio
async def test_get_finding_returns_404_for_unknown_id(http_client):
    fake_id = str(uuid.uuid4())
    response = await http_client.get(f"/api/v1/findings/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_finding_returns_finding(http_client, db_session):
    eng = await _create_engagement(db_session)
    finding = await _create_finding(db_session, eng.id)

    response = await http_client.get(f"/api/v1/findings/{finding.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(finding.id)
    assert data["vulnerability_class"] == "sqli"
    assert data["exploit_detail"] is None


@pytest.mark.asyncio
async def test_get_finding_returns_exploit_detail_when_set(http_client, db_session):
    eng = await _create_engagement(db_session)
    finding = await _create_finding(db_session, eng.id)
    finding.exploit_detail = MOCK_EXPLOIT
    await db_session.commit()

    response = await http_client.get(f"/api/v1/findings/{finding.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["exploit_detail"]["difficulty"] == "easy"


@pytest.mark.asyncio
async def test_generate_exploit_returns_cached_when_already_set(http_client, db_session):
    eng = await _create_engagement(db_session)
    finding = await _create_finding(db_session, eng.id)
    finding.exploit_detail = MOCK_EXPLOIT
    await db_session.commit()

    response = await http_client.post(f"/api/v1/findings/{finding.id}/exploit")
    assert response.status_code == 200
    data = response.json()
    assert data["difficulty"] == "easy"


@pytest.mark.asyncio
async def test_generate_exploit_calls_engine_when_not_cached(http_client, db_session):
    eng = await _create_engagement(db_session)
    finding = await _create_finding(db_session, eng.id)

    mock_engine = MagicMock()
    mock_engine.generate = AsyncMock(return_value=MOCK_EXPLOIT)

    with patch("app.api.findings.ExploitEngine", return_value=mock_engine):
        response = await http_client.post(f"/api/v1/findings/{finding.id}/exploit")

    assert response.status_code == 200
    data = response.json()
    assert data["impact"] == "Data leak"
    mock_engine.generate.assert_called_once()


@pytest.mark.asyncio
async def test_generate_exploit_persists_result(http_client, db_session):
    eng = await _create_engagement(db_session)
    finding = await _create_finding(db_session, eng.id)

    mock_engine = MagicMock()
    mock_engine.generate = AsyncMock(return_value=MOCK_EXPLOIT)

    with patch("app.api.findings.ExploitEngine", return_value=mock_engine):
        await http_client.post(f"/api/v1/findings/{finding.id}/exploit")

    await db_session.refresh(finding)
    assert finding.exploit_detail is not None
    assert finding.exploit_detail["difficulty"] == "easy"


MOCK_POC = {
    "language": "python",
    "filename": "poc_sqli_api_users.py",
    "script": "#!/usr/bin/env python3\nimport requests\n\nTARGET_URL = 'https://example.com'\n\ndef exploit():\n    r = requests.get(f'{TARGET_URL}/api/users', params={'id': \"1' OR '1'='1\"})\n    print(r.json())\n\nif __name__ == '__main__':\n    exploit()",
    "setup": ["pip install requests"],
    "notes": "Replace TARGET_URL before running.",
    "sequence_diagram": "sequenceDiagram\n  participant Attacker\n  participant Server\n  Attacker->>Server: GET /api/users?id=1' OR '1'='1\n  Server-->>Attacker: 200 OK",
}


@pytest.mark.asyncio
async def test_get_poc_returns_404_for_unknown_finding(http_client):
    fake_id = str(uuid.uuid4())
    response = await http_client.get(f"/api/v1/findings/{fake_id}/poc")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_poc_returns_null_when_not_generated(http_client, db_session):
    eng = await _create_engagement(db_session)
    finding = await _create_finding(db_session, eng.id)

    response = await http_client.get(f"/api/v1/findings/{finding.id}/poc")
    assert response.status_code == 200
    data = response.json()
    assert data["poc_detail"] is None


@pytest.mark.asyncio
async def test_get_poc_returns_poc_detail_when_set(http_client, db_session):
    eng = await _create_engagement(db_session)
    finding = await _create_finding(db_session, eng.id)
    finding.poc_detail = MOCK_POC
    await db_session.commit()

    response = await http_client.get(f"/api/v1/findings/{finding.id}/poc")
    assert response.status_code == 200
    data = response.json()
    assert data["poc_detail"]["language"] == "python"
    assert data["poc_detail"]["filename"] == "poc_sqli_api_users.py"


@pytest.mark.asyncio
async def test_generate_poc_returns_cached_when_already_set(http_client, db_session):
    eng = await _create_engagement(db_session)
    finding = await _create_finding(db_session, eng.id)
    finding.poc_detail = MOCK_POC
    await db_session.commit()

    response = await http_client.post(f"/api/v1/findings/{finding.id}/poc")
    assert response.status_code == 200
    data = response.json()
    assert data["language"] == "python"
    assert data["filename"] == "poc_sqli_api_users.py"


@pytest.mark.asyncio
async def test_generate_poc_calls_engine_when_not_cached(http_client, db_session):
    eng = await _create_engagement(db_session)
    finding = await _create_finding(db_session, eng.id)

    mock_engine = MagicMock()
    mock_engine.generate = AsyncMock(return_value=MOCK_POC)

    with patch("app.api.findings.PoCEngine", return_value=mock_engine):
        response = await http_client.post(f"/api/v1/findings/{finding.id}/poc")

    assert response.status_code == 200
    data = response.json()
    assert data["script"].startswith("#!/usr/bin/env python3")
    mock_engine.generate.assert_called_once()


@pytest.mark.asyncio
async def test_generate_poc_persists_result(http_client, db_session):
    eng = await _create_engagement(db_session)
    finding = await _create_finding(db_session, eng.id)

    mock_engine = MagicMock()
    mock_engine.generate = AsyncMock(return_value=MOCK_POC)

    with patch("app.api.findings.PoCEngine", return_value=mock_engine):
        await http_client.post(f"/api/v1/findings/{finding.id}/poc")

    await db_session.refresh(finding)
    assert finding.poc_detail is not None
    assert finding.poc_detail["language"] == "python"


# --- Plan 11: Live Exploitation endpoints ---

@pytest.mark.asyncio
async def test_generate_exploit_script_returns_404_for_unknown_finding(http_client):
    fake_id = str(uuid.uuid4())
    response = await http_client.post(f"/api/v1/findings/{fake_id}/exploit/generate")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_generate_exploit_script_calls_engine_and_caches(http_client, db_session):
    eng = await _create_engagement(db_session)
    finding = await _create_finding(db_session, eng.id)

    mock_script = {
        "language": "python",
        "filename": "exploit_sqli_api_users.py",
        "script": "#!/usr/bin/env python3\nprint('exploiting')",
        "setup": ["pip install requests"],
        "expected_output": "Full credential table",
        "impact_achieved": "Complete database exfiltration",
    }

    with patch("app.api.findings.ExploitScriptEngine") as MockEngine:
        instance = MockEngine.return_value
        instance.generate = AsyncMock(return_value=mock_script)
        response = await http_client.post(f"/api/v1/findings/{finding.id}/exploit/generate")

    assert response.status_code == 200
    data = response.json()
    assert data["language"] == "python"
    assert data["filename"] == "exploit_sqli_api_users.py"

    # Second call must return cached — engine NOT called again
    with patch("app.api.findings.ExploitScriptEngine") as MockEngine2:
        instance2 = MockEngine2.return_value
        instance2.generate = AsyncMock(return_value=mock_script)
        response2 = await http_client.post(f"/api/v1/findings/{finding.id}/exploit/generate")
        MockEngine2.assert_not_called()

    assert response2.status_code == 200


@pytest.mark.asyncio
async def test_execute_exploit_requires_confirmation(http_client, db_session):
    eng = await _create_engagement(db_session)
    finding = await _create_finding(db_session, eng.id)

    # No confirmed=true → requires_confirmation
    response = await http_client.post(
        f"/api/v1/findings/{finding.id}/exploit/execute",
        json={},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["requires_confirmation"] is True


@pytest.mark.asyncio
async def test_execute_exploit_confirmed_runs_and_persists(http_client, db_session):
    eng = await _create_engagement(db_session)
    finding = await _create_finding(db_session, eng.id)

    mock_script = {
        "language": "python",
        "filename": "exploit_sqli_api_users.py",
        "script": "print('data')",
        "setup": [],
        "expected_output": "credentials",
        "impact_achieved": "DB dump",
    }
    mock_execution = {
        "stdout": "admin:$2b$hash",
        "stderr": "",
        "exit_code": 0,
        "timed_out": False,
        "executed_at": "2026-04-16T12:00:00+00:00",
    }
    mock_verdict = {
        "verdict": "confirmed",
        "confidence": 0.95,
        "reasoning": "Credentials extracted.",
    }

    with (
        patch("app.api.findings.ExploitScriptEngine") as MockScriptEngine,
        patch("app.api.findings.ExploitExecutor") as MockExecutor,
        patch("app.api.findings.ExecutionJudge") as MockJudge,
    ):
        MockScriptEngine.return_value.generate = AsyncMock(return_value=mock_script)
        MockExecutor.return_value.execute = AsyncMock(return_value=mock_execution)
        MockJudge.return_value.judge = AsyncMock(return_value=mock_verdict)

        response = await http_client.post(
            f"/api/v1/findings/{finding.id}/exploit/execute",
            json={"confirmed": True},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["verdict"] == "confirmed"
    assert data["confidence"] == 0.95
    assert "stdout" in data
    assert "executed_at" in data


@pytest.mark.asyncio
async def test_override_verdict_updates_exploit_execution(http_client, db_session):
    eng = await _create_engagement(db_session)
    finding = await _create_finding(db_session, eng.id)

    # Seed exploit_execution directly
    from sqlalchemy import select
    from app.models.finding import Finding as FindingModel
    result = await db_session.execute(select(FindingModel).where(FindingModel.id == finding.id))
    f = result.scalar_one()
    f.exploit_execution = {
        "stdout": "output",
        "stderr": "",
        "exit_code": 0,
        "timed_out": False,
        "verdict": "inconclusive",
        "confidence": 0.5,
        "reasoning": "unclear",
        "executed_at": "2026-04-16T12:00:00+00:00",
        "override_verdict": None,
    }
    await db_session.commit()

    response = await http_client.patch(
        f"/api/v1/findings/{finding.id}/exploit/execution",
        json={"verdict": "confirmed"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["override_verdict"] == "confirmed"
