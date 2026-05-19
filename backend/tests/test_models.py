from app.database import Base
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


def test_org_llm_models_registered():
    from app.models import org_llm, llm_usage  # noqa: F401
    table_names = set(Base.metadata.tables.keys())
    assert "org_llm_credentials" in table_names
    assert "org_llm_task_config" in table_names
    assert "org_llm_audit_log" in table_names
    assert "llm_usage_events" in table_names


def test_no_postgres_uuid_dialect():
    """All models must use portable sqlalchemy.Uuid, not dialects.postgresql.UUID."""
    import importlib
    import inspect
    import pkgutil
    import app.models as models_pkg
    for _, mod_name, _ in pkgutil.iter_modules(models_pkg.__path__):
        mod = importlib.import_module(f"app.models.{mod_name}")
        source = inspect.getsource(mod)
        assert "dialects.postgresql" not in source, (
            f"app/models/{mod_name}.py imports from dialects.postgresql — "
            "use 'from sqlalchemy import Uuid' instead"
        )
