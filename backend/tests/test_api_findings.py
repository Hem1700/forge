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
