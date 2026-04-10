from app.models.engagement import Engagement, EngagementStatus, GateStatus
from app.models.agent import Agent, AgentType, AgentStatus
from app.models.task import Task, Bid, TaskStatus, Priority
from app.models.finding import Finding, Severity, ValidationStatus
from app.models.knowledge import KnowledgeGraphEntry, OutcomeType
import uuid

def test_engagement_defaults():
    e = Engagement(target_url="https://example.com")
    assert e.status == EngagementStatus.pending
    assert e.gate_status == GateStatus.gate_1
    assert e.semantic_model == {}

def test_task_defaults():
    t = Task(
        engagement_id=uuid.uuid4(),
        title="Test JWT bypass",
        surface="/api/auth",
        required_confidence=0.7,
        created_by=uuid.uuid4(),
    )
    assert t.status == TaskStatus.open
    assert t.priority == Priority.medium

def test_finding_defaults():
    f = Finding(
        engagement_id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        agent_id=uuid.uuid4(),
        title="SQL Injection",
        vulnerability_class="sqli",
        affected_surface="/api/users",
    )
    assert f.validation_status == ValidationStatus.pending
    assert f.confidence_score == 0.0
