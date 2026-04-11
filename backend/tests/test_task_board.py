# backend/tests/test_task_board.py
import pytest
import uuid
from app.swarm.task_board import TaskBoard


@pytest.mark.asyncio
async def test_publish_task():
    board = TaskBoard()
    task_id = str(uuid.uuid4())
    engagement_id = str(uuid.uuid4())
    creator_id = str(uuid.uuid4())
    await board.publish_task(
        task_id=task_id,
        engagement_id=engagement_id,
        title="Test JWT bypass",
        surface="/api/auth/refresh",
        required_confidence=0.7,
        priority="high",
        created_by=creator_id,
    )
    tasks = await board.get_open_tasks(engagement_id)
    assert any(t["task_id"] == task_id for t in tasks)


@pytest.mark.asyncio
async def test_submit_and_resolve_bid():
    board = TaskBoard()
    task_id = str(uuid.uuid4())
    engagement_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    creator_id = str(uuid.uuid4())

    await board.publish_task(
        task_id=task_id,
        engagement_id=engagement_id,
        title="IDOR test",
        surface="/api/users/{id}",
        required_confidence=0.6,
        priority="medium",
        created_by=creator_id,
    )
    await board.submit_bid(
        task_id=task_id,
        agent_id=agent_id,
        confidence=0.85,
        basis="3 prior IDOR confirmations on similar APIs",
        estimated_probes=4,
        noise_level="low",
    )
    bids = await board.get_bids(task_id)
    assert len(bids) == 1
    assert bids[0]["confidence"] == 0.85


@pytest.mark.asyncio
async def test_assign_task():
    board = TaskBoard()
    task_id = str(uuid.uuid4())
    engagement_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    creator_id = str(uuid.uuid4())

    await board.publish_task(
        task_id=task_id, engagement_id=engagement_id,
        title="XSS probe", surface="/search",
        required_confidence=0.5, priority="low", created_by=creator_id,
    )
    await board.assign_task(task_id=task_id, agent_id=agent_id)
    task = await board.get_task(task_id)
    assert task["status"] == "assigned"
    assert task["assigned_agent_id"] == agent_id
