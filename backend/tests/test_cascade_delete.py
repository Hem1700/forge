# backend/tests/test_cascade_delete.py
"""Verify that deleting an engagement cascades to all child rows."""
from __future__ import annotations

import uuid
import pytest
from sqlalchemy import select, text

from app.models.engagement import Engagement, EngagementStatus
from app.models.finding import Finding, Severity, ValidationStatus
from app.models.task import Task, TaskStatus, Priority
from app.models.agent import Agent, AgentType, AgentStatus
from app.models.knowledge import KnowledgeGraphEntry, OutcomeType
from app.models.engagement_event import EngagementEvent
from app.models.organization import Organization


async def _make_engagement(db, org_id) -> Engagement:
    eng = Engagement(
        org_id=org_id,
        target_url="https://cascade-test.example.com",
        target_type="web",
        status=EngagementStatus.pending,
    )
    db.add(eng)
    await db.commit()
    await db.refresh(eng)
    return eng


async def _populate_children(db, eng: Engagement) -> None:
    agent = Agent(
        engagement_id=eng.id,
        type=AgentType.recon,
        spawned_reason="cascade test",
        status=AgentStatus.idle,
        tools=[],
    )
    db.add(agent)
    await db.flush()

    task = Task(
        engagement_id=eng.id,
        title="cascade task",
        description="",
        surface="/",
        priority=Priority.medium,
        status=TaskStatus.open,
        created_by=agent.id,
    )
    db.add(task)
    await db.flush()

    finding = Finding(
        engagement_id=eng.id,
        task_id=task.id,
        agent_id=agent.id,
        title="cascade finding",
        description="",
        vulnerability_class="test",
        affected_surface="/test",
        severity=Severity.low,
        validation_status=ValidationStatus.pending,
    )
    db.add(finding)

    knowledge = KnowledgeGraphEntry(
        engagement_id=eng.id,
        attack_class="xss",
        technique="reflected",
        outcome=OutcomeType.confirmed,
    )
    db.add(knowledge)

    event = EngagementEvent(
        engagement_id=eng.id,
        type="test_event",
        payload={"msg": "hi"},
    )
    db.add(event)

    await db.commit()


@pytest.mark.asyncio
async def test_delete_engagement_cascades_to_children(db_session):
    """Deleting an engagement must remove findings, tasks, agents, knowledge, and events."""
    org = Organization(name=f"cascade-org-{uuid.uuid4()}")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    eng = await _make_engagement(db_session, org.id)
    eng_id = eng.id
    await _populate_children(db_session, eng)

    # Confirm children exist
    assert (await db_session.execute(select(Finding).where(Finding.engagement_id == eng_id))).scalars().first() is not None
    assert (await db_session.execute(select(Task).where(Task.engagement_id == eng_id))).scalars().first() is not None
    assert (await db_session.execute(select(Agent).where(Agent.engagement_id == eng_id))).scalars().first() is not None
    assert (await db_session.execute(select(KnowledgeGraphEntry).where(KnowledgeGraphEntry.engagement_id == eng_id))).scalars().first() is not None
    assert (await db_session.execute(select(EngagementEvent).where(EngagementEvent.engagement_id == eng_id))).scalars().first() is not None

    # Delete via ORM (triggers cascade="all, delete-orphan")
    await db_session.delete(eng)
    await db_session.commit()

    # All children must be gone
    assert (await db_session.execute(select(Finding).where(Finding.engagement_id == eng_id))).scalars().first() is None
    assert (await db_session.execute(select(Task).where(Task.engagement_id == eng_id))).scalars().first() is None
    assert (await db_session.execute(select(Agent).where(Agent.engagement_id == eng_id))).scalars().first() is None
    assert (await db_session.execute(select(KnowledgeGraphEntry).where(KnowledgeGraphEntry.engagement_id == eng_id))).scalars().first() is None
    assert (await db_session.execute(select(EngagementEvent).where(EngagementEvent.engagement_id == eng_id))).scalars().first() is None


@pytest.mark.asyncio
async def test_delete_engagement_via_raw_sql_cascades(db_session):
    """DB-level CASCADE: raw DELETE statement must also remove children."""
    org = Organization(name=f"cascade-org-raw-{uuid.uuid4()}")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    eng = await _make_engagement(db_session, org.id)
    eng_id = eng.id
    await _populate_children(db_session, eng)

    # Raw SQL DELETE bypasses ORM cascade but hits the DB-level ON DELETE CASCADE
    await db_session.execute(
        text("DELETE FROM engagements WHERE id = :eid"),
        {"eid": str(eng_id)},
    )
    await db_session.commit()

    assert (await db_session.execute(select(Finding).where(Finding.engagement_id == eng_id))).scalars().first() is None
    assert (await db_session.execute(select(Task).where(Task.engagement_id == eng_id))).scalars().first() is None
    assert (await db_session.execute(select(Agent).where(Agent.engagement_id == eng_id))).scalars().first() is None
