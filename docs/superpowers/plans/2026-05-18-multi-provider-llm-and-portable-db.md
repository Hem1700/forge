# Multi-Provider LLM & Portable DB Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all hardcoded `ChatAnthropic` instantiations with a `get_llm()` factory that resolves provider/model from per-org DB config, and swap PostgreSQL-only UUID types for portable SQLAlchemy `Uuid`.

**Architecture:** A single `app/brain/llm_factory.py` module owns provider resolution (DB lookup → env fallback), credential decryption (Fernet), retry logic (exponential backoff), and usage logging. Each brain/swarm/validator module calls `await get_llm(TaskType.X, org_id=...)` instead of constructing `ChatAnthropic` directly. Four new tables store org credentials, per-task model config, an audit log, and usage events.

**Tech Stack:** SQLAlchemy 2.x `Uuid` type (Postgres + MySQL portable), Fernet (cryptography package, already installed), langchain-openai, langchain-aws, asyncmy (MySQL driver), FastAPI APIRouter, Click (CLI)

---

## File Map

**New files:**
- `backend/app/brain/llm_factory.py` — core factory: types, resolution, builders, retry, tracking
- `backend/app/models/org_llm.py` — OrgLLMCredential, OrgLLMTaskConfig, OrgLLMAuditLog models
- `backend/app/models/llm_usage.py` — LLMUsageEvent model
- `backend/app/api/org_llm.py` — REST endpoints `/api/v1/org/llm/`
- `backend/cli/forge_cli/commands/org_llm.py` — CLI `forge org llm` commands
- `backend/tests/test_llm_factory.py` — factory unit tests
- `backend/tests/test_org_llm_endpoints.py` — API endpoint tests
- `backend/alembic/versions/<hash>_add_org_llm_tables.py` — migration

**Modified files:**
- `backend/requirements.txt` — add langchain-openai, langchain-aws, asyncmy
- `backend/app/config.py` — add forge_secrets_key, openai_api_key, aws_*, azure_* env vars
- `backend/alembic/env.py` — import new models
- `backend/tests/conftest.py` — add mock_llm fixture
- `backend/app/main.py` — register org_llm router
- `backend/app/brain/agent_brain.py` — replace ChatAnthropic with get_llm
- `backend/app/brain/campaign_planner.py` — replace ChatAnthropic
- `backend/app/brain/codebase_modeler.py` — replace ChatAnthropic, remove _LLMWrapper export
- `backend/app/brain/evasion_strategist.py` — replace ChatAnthropic
- `backend/app/brain/execution_judge.py` — replace ChatAnthropic
- `backend/app/brain/exploit_engine.py` — replace ChatAnthropic
- `backend/app/brain/exploit_script_engine.py` — replace ChatAnthropic
- `backend/app/brain/findings_judge.py` — replace ChatAnthropic
- `backend/app/brain/poc_engine.py` — replace ChatAnthropic
- `backend/app/brain/semantic_modeler.py` — replace ChatAnthropic
- `backend/app/swarm/agents/code_analyzer.py` — replace ChatAnthropic
- `backend/app/swarm/agents/logic_modeler.py` — replace ChatAnthropic
- `backend/app/validator/severity.py` — replace ChatAnthropic
- `backend/app/validator/challenger.py` — replace ChatAnthropic
- `backend/app/api/start.py` — pass org_id to brain constructors
- `backend/app/api/findings.py` — pass org_id to brain constructors
- `backend/app/models/organization.py` — UUID → Uuid portability swap
- `backend/app/models/user.py` — UUID → Uuid
- `backend/app/models/engagement.py` — UUID → Uuid
- `backend/app/models/task.py` — UUID → Uuid
- `backend/app/models/finding.py` — UUID → Uuid
- `backend/app/models/agent.py` — UUID → Uuid
- `backend/app/models/api_key.py` — UUID → Uuid
- `backend/app/models/knowledge.py` — UUID → Uuid
- `backend/tests/test_brain.py` — switch to mock_llm fixture
- `backend/tests/test_agent_brain.py` — switch to mock_llm fixture
- `backend/tests/test_exploit_script_engine.py` — switch to mock_llm fixture
- `backend/cli/forge_cli/main.py` — register org_llm group

---

## Task 1: Add dependencies and update config

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add new Python packages to requirements.txt**

```
# backend/requirements.txt — add after langchain-anthropic line:
langchain-openai==0.2.9
langchain-aws==0.2.7
asyncmy==0.2.10
```

- [ ] **Step 2: Add new settings to config.py**

Replace the entire `backend/app/config.py` with:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://forge:forge@localhost:5432/forge"
    redis_url: str = "redis://localhost:6379"
    qdrant_url: str = "http://localhost:6333"
    neo4j_url: str = "bolt://localhost:17687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "forge_password"
    # LLM — deployment-level fallback keys (org overrides stored in DB)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    # Fernet master key for encrypting org LLM credentials in the DB.
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    forge_secrets_key: str = ""
    # Legacy / local
    use_local_llm: bool = False
    ollama_url: str = "http://localhost:11434"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    confidence_threshold: float = 0.75
    thread_death_threshold: int = 5
    frontend_url: str = "http://localhost:5173"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 3: Commit**

```bash
cd backend
git add requirements.txt app/config.py
git commit -m "feat: add langchain-openai/aws/asyncmy deps and multi-provider settings"
```

---

## Task 2: Create ORM models for org LLM tables

**Files:**
- Create: `backend/app/models/org_llm.py`
- Create: `backend/app/models/llm_usage.py`

- [ ] **Step 1: Write test for model existence (verify tables register correctly)**

Add to `backend/tests/test_models.py` (append, don't overwrite):

```python
def test_org_llm_models_registered():
    from app.database import Base
    from app.models import org_llm, llm_usage  # noqa: F401
    table_names = set(Base.metadata.tables.keys())
    assert "org_llm_credentials" in table_names
    assert "org_llm_task_config" in table_names
    assert "org_llm_audit_log" in table_names
    assert "llm_usage_events" in table_names
```

- [ ] **Step 2: Run to verify fails**

```bash
cd backend && python -m pytest tests/test_models.py::test_org_llm_models_registered -v
```

Expected: `ImportError` or `AssertionError` (tables don't exist yet).

- [ ] **Step 3: Create backend/app/models/org_llm.py**

```python
# backend/app/models/org_llm.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, JSON, LargeBinary, String, Float, Integer, UniqueConstraint
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OrgLLMCredential(Base):
    __tablename__ = "org_llm_credentials"
    __table_args__ = (UniqueConstraint("org_id", "provider"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    encrypted_key: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrgLLMTaskConfig(Base):
    __tablename__ = "org_llm_task_config"
    __table_args__ = (UniqueConstraint("org_id", "task_type"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrgLLMAuditLog(Base):
    __tablename__ = "org_llm_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 4: Create backend/app/models/llm_usage.py**

```python
# backend/app/models/llm_usage.py
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Numeric, String, Integer
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LLMUsageEvent(Base):
    __tablename__ = "llm_usage_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    task: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 5: Run test to verify passes**

```bash
cd backend && python -m pytest tests/test_models.py::test_org_llm_models_registered -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/models/org_llm.py app/models/llm_usage.py tests/test_models.py
git commit -m "feat: add ORM models for org LLM credentials, task config, audit log, usage events"
```

---

## Task 3: Alembic migration for the 4 new tables

**Files:**
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/<hash>_add_org_llm_tables.py`

- [ ] **Step 1: Update alembic/env.py to import new models**

In `backend/alembic/env.py`, update the model import line (line 12):

```python
# OLD:
from app.models import engagement, agent, task, finding, knowledge, user, api_key, organization  # noqa

# NEW:
from app.models import engagement, agent, task, finding, knowledge, user, api_key, organization, org_llm, llm_usage  # noqa
```

- [ ] **Step 2: Generate migration**

```bash
cd backend
alembic revision --autogenerate -m "add_org_llm_tables"
```

Expected: A new file created at `alembic/versions/<hash>_add_org_llm_tables.py`.

- [ ] **Step 3: Verify the generated migration looks correct**

Open the generated file and verify it creates four tables: `org_llm_credentials`, `org_llm_task_config`, `org_llm_audit_log`, `llm_usage_events`. If the autogenerated migration is missing tables or has wrong column types, edit it to match:

```python
def upgrade() -> None:
    op.create_table(
        'org_llm_credentials',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('org_id', sa.Uuid(), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('encrypted_key', sa.LargeBinary(), nullable=True),
        sa.Column('region', sa.String(length=50), nullable=True),
        sa.Column('endpoint', sa.String(length=500), nullable=True),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.Column('last_tested_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('org_id', 'provider'),
    )
    op.create_index(op.f('ix_org_llm_credentials_org_id'), 'org_llm_credentials', ['org_id'])
    op.create_table(
        'org_llm_task_config',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('org_id', sa.Uuid(), nullable=False),
        sa.Column('task_type', sa.String(length=50), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('max_tokens', sa.Integer(), nullable=True),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('org_id', 'task_type'),
    )
    op.create_index(op.f('ix_org_llm_task_config_org_id'), 'org_llm_task_config', ['org_id'])
    op.create_table(
        'org_llm_audit_log',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('org_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_org_llm_audit_log_org_id'), 'org_llm_audit_log', ['org_id'])
    op.create_table(
        'llm_usage_events',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('org_id', sa.Uuid(), nullable=False),
        sa.Column('engagement_id', sa.Uuid(), nullable=True),
        sa.Column('task', sa.String(length=50), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('cost_usd', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_llm_usage_events_org_id'), 'llm_usage_events', ['org_id'])
    op.create_index(op.f('ix_llm_usage_events_engagement_id'), 'llm_usage_events', ['engagement_id'])


def downgrade() -> None:
    op.drop_table('llm_usage_events')
    op.drop_table('org_llm_audit_log')
    op.drop_table('org_llm_task_config')
    op.drop_table('org_llm_credentials')
```

- [ ] **Step 4: Run the migration**

```bash
cd backend && alembic upgrade head
```

Expected: Migration runs without errors. Check with `alembic current` — should show the latest revision.

- [ ] **Step 5: Commit**

```bash
git add alembic/env.py alembic/versions/
git commit -m "feat: alembic migration for org_llm_credentials, task_config, audit_log, usage_events"
```

---

## Task 4: Create llm_factory.py (complete implementation)

**Files:**
- Create: `backend/app/brain/llm_factory.py`

- [ ] **Step 1: Write failing test for factory skeleton**

Create `backend/tests/test_llm_factory.py`:

```python
# backend/tests/test_llm_factory.py
"""Unit tests for the LLM factory — resolution, builders, retry, tracking."""
from __future__ import annotations
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage

from app.brain.llm_factory import (
    TaskType, Provider, LLMSpec, ProviderCreds,
    DEFAULT_TASK_SPECS, get_llm, RetryLLM, TrackedLLM,
    _resolve_spec, _resolve_credentials,
)


# ── Resolution ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_spec_no_org_returns_default():
    spec = await _resolve_spec(TaskType.codebase_modeling, org_id=None)
    assert spec.provider == Provider.anthropic
    assert spec.model == "claude-sonnet-4-6"
    assert spec.max_tokens == 8000


@pytest.mark.asyncio
async def test_resolve_spec_no_org_haiku_for_judge():
    spec = await _resolve_spec(TaskType.findings_judge, org_id=None)
    assert spec.model == "claude-haiku-4-5"


@pytest.mark.asyncio
async def test_resolve_spec_org_override(monkeypatch):
    import uuid
    org_id = uuid.uuid4()

    fake_row = MagicMock()
    fake_row.provider = "openai"
    fake_row.model = "gpt-4-turbo"
    fake_row.max_tokens = 3000
    fake_row.temperature = 0.0

    async def fake_db_execute(*a, **kw):
        result = MagicMock()
        result.scalar_one_or_none.return_value = fake_row
        return result

    fake_session = AsyncMock()
    fake_session.execute = fake_db_execute

    class FakeCtx:
        async def __aenter__(self): return fake_session
        async def __aexit__(self, *a): pass

    monkeypatch.setattr("app.brain.llm_factory.AsyncSessionLocal", lambda: FakeCtx())

    spec = await _resolve_spec(TaskType.codebase_modeling, org_id=org_id)
    assert spec.provider == Provider.openai
    assert spec.model == "gpt-4-turbo"


@pytest.mark.asyncio
async def test_resolve_credentials_no_org_falls_back_to_env(monkeypatch):
    monkeypatch.setattr("app.brain.llm_factory._ENV_CREDS", {
        Provider.anthropic: ProviderCreds(provider=Provider.anthropic, api_key="test-key"),
    })
    creds = await _resolve_credentials(Provider.anthropic, org_id=None)
    assert creds.api_key == "test-key"


@pytest.mark.asyncio
async def test_resolve_credentials_org_decrypts_key(monkeypatch):
    import uuid
    from cryptography.fernet import Fernet

    key = Fernet.generate_key()
    f = Fernet(key)
    encrypted = f.encrypt(b"my-secret-api-key")

    org_id = uuid.uuid4()
    fake_row = MagicMock()
    fake_row.encrypted_key = encrypted
    fake_row.region = None
    fake_row.endpoint = None
    fake_row.extra = {}

    async def fake_db_execute(*a, **kw):
        result = MagicMock()
        result.scalar_one_or_none.return_value = fake_row
        return result

    fake_session = AsyncMock()
    fake_session.execute = fake_db_execute

    class FakeCtx:
        async def __aenter__(self): return fake_session
        async def __aexit__(self, *a): pass

    monkeypatch.setattr("app.brain.llm_factory.AsyncSessionLocal", lambda: FakeCtx())
    monkeypatch.setattr("app.brain.llm_factory._fernet", f)

    creds = await _resolve_credentials(Provider.anthropic, org_id=org_id)
    assert creds.api_key == "my-secret-api-key"


# ── Retry ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_retry_llm_succeeds_on_first_try():
    inner = AsyncMock()
    inner.ainvoke = AsyncMock(return_value=AIMessage(content="ok"))
    retry = RetryLLM(inner, retries=3, backoff_base=0.01)
    result = await retry.ainvoke([])
    assert result.content == "ok"
    assert inner.ainvoke.call_count == 1


@pytest.mark.asyncio
async def test_retry_llm_retries_on_rate_limit():
    class FakeRateLimitError(Exception):
        pass
    FakeRateLimitError.__name__ = "RateLimitError"

    inner = AsyncMock()
    inner.ainvoke = AsyncMock(
        side_effect=[FakeRateLimitError("429"), FakeRateLimitError("429"), AIMessage(content="ok")]
    )
    retry = RetryLLM(inner, retries=3, backoff_base=0.001)
    result = await retry.ainvoke([])
    assert result.content == "ok"
    assert inner.ainvoke.call_count == 3


@pytest.mark.asyncio
async def test_retry_llm_raises_after_max_retries():
    class FakeRateLimitError(Exception):
        pass
    FakeRateLimitError.__name__ = "RateLimitError"

    inner = AsyncMock()
    inner.ainvoke = AsyncMock(side_effect=FakeRateLimitError("429"))
    retry = RetryLLM(inner, retries=2, backoff_base=0.001)
    with pytest.raises(FakeRateLimitError):
        await retry.ainvoke([])
    assert inner.ainvoke.call_count == 3  # initial + 2 retries


# ── Tracking ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tracked_llm_logs_usage(monkeypatch):
    import uuid
    logged = []

    async def fake_log_usage(**kwargs):
        logged.append(kwargs)

    monkeypatch.setattr("app.brain.llm_factory._log_usage", fake_log_usage)

    inner = AsyncMock()
    response = MagicMock()
    response.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
    inner.ainvoke = AsyncMock(return_value=response)

    org_id = uuid.uuid4()
    tracked = TrackedLLM(
        inner,
        task=TaskType.codebase_modeling,
        org_id=org_id,
        engagement_id=None,
        provider=Provider.anthropic,
        model="claude-sonnet-4-6",
    )
    await tracked.ainvoke([])

    assert len(logged) == 1
    assert logged[0]["input_tokens"] == 10
    assert logged[0]["output_tokens"] == 5
    assert logged[0]["org_id"] == org_id


# ── get_llm integration ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_llm_returns_tracked_llm(monkeypatch):
    fake_raw = AsyncMock()
    fake_raw.ainvoke = AsyncMock(return_value=MagicMock(
        content="hi", usage_metadata={"input_tokens": 1, "output_tokens": 1}
    ))

    monkeypatch.setattr("app.brain.llm_factory._BUILDERS", {
        Provider.anthropic: lambda spec, creds: fake_raw,
    })
    monkeypatch.setattr("app.brain.llm_factory._log_usage", AsyncMock())

    llm = await get_llm(TaskType.codebase_modeling, org_id=None)
    assert isinstance(llm, TrackedLLM)
```

- [ ] **Step 2: Run to verify fails**

```bash
cd backend && python -m pytest tests/test_llm_factory.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'TaskType' from 'app.brain.llm_factory'`

- [ ] **Step 3: Create backend/app/brain/llm_factory.py**

```python
# backend/app/brain/llm_factory.py
"""LLM factory — resolves provider/model per org, wraps for retry and usage tracking."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from enum import Enum

from cryptography.fernet import Fernet
from pydantic import BaseModel
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


# ── Enums and types ───────────────────────────────────────────────────────────

class TaskType(str, Enum):
    codebase_modeling   = "codebase_modeling"
    campaign_planning   = "campaign_planning"
    code_analyzer       = "code_analyzer"
    semantic_modeler    = "semantic_modeler"
    findings_judge      = "findings_judge"
    execution_judge     = "execution_judge"
    exploit_engine      = "exploit_engine"
    exploit_script      = "exploit_script"
    poc_engine          = "poc_engine"
    evasion_strategist  = "evasion_strategist"
    logic_modeler       = "logic_modeler"
    agent_brain         = "agent_brain"
    challenger          = "challenger"
    severity_assessor   = "severity_assessor"


class Provider(str, Enum):
    anthropic = "anthropic"
    openai    = "openai"
    bedrock   = "bedrock"
    azure     = "azure"


class LLMSpec(BaseModel):
    provider: Provider
    model: str
    max_tokens: int = 4000
    temperature: float = 0.0


class ProviderCreds(BaseModel):
    provider: Provider
    api_key: str | None = None
    region: str | None = None
    endpoint: str | None = None
    use_iam_role: bool = False
    extra: dict = {}


# ── Default task → spec mapping (Balanced preset) ────────────────────────────

DEFAULT_TASK_SPECS: dict[TaskType, LLMSpec] = {
    TaskType.codebase_modeling:  LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=8000),
    TaskType.code_analyzer:      LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=4000),
    TaskType.exploit_engine:     LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=6000),
    TaskType.exploit_script:     LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=4000),
    TaskType.poc_engine:         LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=4000),
    TaskType.agent_brain:        LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=4000),
    TaskType.semantic_modeler:   LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=3000),
    TaskType.campaign_planning:  LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=3000),
    TaskType.evasion_strategist: LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=3500),
    TaskType.logic_modeler:      LLMSpec(provider=Provider.anthropic, model="claude-sonnet-4-6", max_tokens=2000),
    TaskType.findings_judge:     LLMSpec(provider=Provider.anthropic, model="claude-haiku-4-5", max_tokens=2500),
    TaskType.execution_judge:    LLMSpec(provider=Provider.anthropic, model="claude-haiku-4-5", max_tokens=2000),
    TaskType.severity_assessor:  LLMSpec(provider=Provider.anthropic, model="claude-haiku-4-5", max_tokens=500),
    TaskType.challenger:         LLMSpec(provider=Provider.anthropic, model="claude-haiku-4-5", max_tokens=500),
}

# Smart/cheap model pairs per provider (for preset application)
_SMART_MODELS: dict[Provider, str] = {
    Provider.anthropic: "claude-sonnet-4-6",
    Provider.openai:    "gpt-4-turbo",
    Provider.bedrock:   "anthropic.claude-sonnet-4",
    Provider.azure:     "gpt-4-turbo",
}
_CHEAP_MODELS: dict[Provider, str] = {
    Provider.anthropic: "claude-haiku-4-5",
    Provider.openai:    "gpt-4o-mini",
    Provider.bedrock:   "anthropic.claude-haiku-4",
    Provider.azure:     "gpt-4o-mini",
}


# ── Cost pricing table (USD per 1M tokens: input, output) ────────────────────

_PRICING: dict[tuple[Provider, str], tuple[float, float]] = {
    (Provider.anthropic, "claude-sonnet-4-6"): (3.0, 15.0),
    (Provider.anthropic, "claude-haiku-4-5"):  (0.25, 1.25),
    (Provider.openai,    "gpt-4-turbo"):       (10.0, 30.0),
    (Provider.openai,    "gpt-4o-mini"):       (0.15, 0.6),
}


def _price(provider: Provider, model: str, usage: dict) -> float:
    pair = _PRICING.get((provider, model))
    if not pair:
        return 0.0
    inp, out = pair
    return (usage.get("input_tokens", 0) * inp + usage.get("output_tokens", 0) * out) / 1_000_000


# ── Fernet encryption ─────────────────────────────────────────────────────────

_fernet: Fernet | None = None
if settings.forge_secrets_key:
    _key = settings.forge_secrets_key
    _fernet = Fernet(_key.encode("ascii") if isinstance(_key, str) else _key)
elif not any([settings.anthropic_api_key, settings.openai_api_key, settings.aws_access_key_id]):
    logger.warning(
        "FORGE_SECRETS_KEY is not set and no deployment-level API keys found. "
        "LLM calls will fail unless at least one provider key is configured."
    )


# ── Env-var fallback credentials ──────────────────────────────────────────────

_ENV_CREDS: dict[Provider, ProviderCreds] = {
    Provider.anthropic: ProviderCreds(
        provider=Provider.anthropic,
        api_key=settings.anthropic_api_key or None,
    ),
    Provider.openai: ProviderCreds(
        provider=Provider.openai,
        api_key=settings.openai_api_key or None,
    ),
    Provider.bedrock: ProviderCreds(
        provider=Provider.bedrock,
        api_key=settings.aws_access_key_id or None,
        region=settings.aws_region,
        use_iam_role=not bool(settings.aws_access_key_id),
        extra={"aws_secret_access_key": settings.aws_secret_access_key},
    ),
    Provider.azure: ProviderCreds(
        provider=Provider.azure,
        api_key=settings.azure_openai_api_key or None,
        endpoint=settings.azure_openai_endpoint or None,
    ),
}


# ── Provider builders ─────────────────────────────────────────────────────────

def _build_anthropic(spec: LLMSpec, creds: ProviderCreds):
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(
        model=spec.model,
        api_key=creds.api_key,
        max_tokens=spec.max_tokens,
        temperature=spec.temperature,
    )


def _build_openai(spec: LLMSpec, creds: ProviderCreds):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=spec.model,
        api_key=creds.api_key,
        max_tokens=spec.max_tokens,
        temperature=spec.temperature,
    )


def _build_bedrock(spec: LLMSpec, creds: ProviderCreds):
    import boto3
    from langchain_aws import ChatBedrock
    region = creds.region or "us-east-1"
    if creds.use_iam_role:
        client = boto3.client("bedrock-runtime", region_name=region)
    else:
        client = boto3.client(
            "bedrock-runtime",
            region_name=region,
            aws_access_key_id=creds.api_key,
            aws_secret_access_key=creds.extra.get("aws_secret_access_key"),
        )
    return ChatBedrock(
        model_id=spec.model,
        client=client,
        model_kwargs={"max_tokens": spec.max_tokens, "temperature": spec.temperature},
    )


def _build_azure(spec: LLMSpec, creds: ProviderCreds):
    from langchain_openai import AzureChatOpenAI
    return AzureChatOpenAI(
        azure_deployment=spec.model,
        azure_endpoint=creds.endpoint or "",
        api_key=creds.api_key,
        max_tokens=spec.max_tokens,
        temperature=spec.temperature,
    )


_BUILDERS = {
    Provider.anthropic: _build_anthropic,
    Provider.openai:    _build_openai,
    Provider.bedrock:   _build_bedrock,
    Provider.azure:     _build_azure,
}


# ── Resolution helpers ────────────────────────────────────────────────────────

async def _resolve_spec(task: TaskType, org_id: uuid.UUID | None) -> LLMSpec:
    if org_id:
        from app.models.org_llm import OrgLLMTaskConfig
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(OrgLLMTaskConfig).where(
                    OrgLLMTaskConfig.org_id == org_id,
                    OrgLLMTaskConfig.task_type == task.value,
                )
            )).scalar_one_or_none()
            if row:
                return LLMSpec(
                    provider=Provider(row.provider),
                    model=row.model,
                    max_tokens=row.max_tokens or DEFAULT_TASK_SPECS[task].max_tokens,
                    temperature=row.temperature or 0.0,
                )
    return DEFAULT_TASK_SPECS[task]


async def _resolve_credentials(provider: Provider, org_id: uuid.UUID | None) -> ProviderCreds:
    if org_id:
        from app.models.org_llm import OrgLLMCredential
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(OrgLLMCredential).where(
                    OrgLLMCredential.org_id == org_id,
                    OrgLLMCredential.provider == provider.value,
                )
            )).scalar_one_or_none()
            if row:
                api_key = None
                if row.encrypted_key and _fernet:
                    api_key = _fernet.decrypt(row.encrypted_key).decode()
                return ProviderCreds(
                    provider=provider,
                    api_key=api_key,
                    region=row.region,
                    endpoint=row.endpoint,
                    use_iam_role=row.extra.get("use_iam_role", False),
                    extra=row.extra or {},
                )
    return _ENV_CREDS[provider]


# ── Retry wrapper ─────────────────────────────────────────────────────────────

class RetryLLM:
    def __init__(self, llm, retries: int = 3, backoff_base: float = 1.0):
        self.llm = llm
        self.retries = retries
        self.backoff_base = backoff_base

    async def ainvoke(self, messages, **kw):
        for attempt in range(self.retries + 1):
            try:
                return await self.llm.ainvoke(messages, **kw)
            except Exception as e:
                if not self._is_rate_limited(e) or attempt == self.retries:
                    raise
                wait = self.backoff_base * (2 ** attempt)
                logger.warning(
                    "LLM rate-limited, retrying in %ss (attempt %d/%d)",
                    wait, attempt + 1, self.retries,
                )
                await asyncio.sleep(wait)

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        return type(exc).__name__ in ("RateLimitError", "APIStatusError")


# ── Usage tracking ────────────────────────────────────────────────────────────

async def _log_usage(
    *,
    org_id: uuid.UUID | None,
    engagement_id: uuid.UUID | None,
    task: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    duration_ms: int,
) -> None:
    if org_id is None:
        return
    from app.models.llm_usage import LLMUsageEvent
    try:
        async with AsyncSessionLocal() as db:
            event = LLMUsageEvent(
                org_id=org_id,
                engagement_id=engagement_id,
                task=task,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                duration_ms=duration_ms,
            )
            db.add(event)
            await db.commit()
    except Exception:
        logger.exception("Failed to log LLM usage event")


class TrackedLLM:
    def __init__(self, llm, *, task: TaskType, org_id, engagement_id, provider: Provider, model: str):
        self.llm = llm
        self.task = task
        self.org_id = org_id
        self.engagement_id = engagement_id
        self.provider = provider
        self.model = model

    async def ainvoke(self, messages, **kw):
        t0 = time.monotonic()
        response = await self.llm.ainvoke(messages, **kw)
        usage = getattr(response, "usage_metadata", {}) or {}
        await _log_usage(
            org_id=self.org_id,
            engagement_id=self.engagement_id,
            task=self.task.value,
            provider=self.provider.value,
            model=self.model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cost_usd=_price(self.provider, self.model, usage),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
        return response


# ── Public API ────────────────────────────────────────────────────────────────

async def get_llm(
    task: TaskType,
    org_id: uuid.UUID | None = None,
    engagement_id: uuid.UUID | None = None,
) -> TrackedLLM:
    """Resolve provider/model for task+org, build LangChain client, wrap for retry+tracking."""
    spec = await _resolve_spec(task, org_id)
    creds = await _resolve_credentials(spec.provider, org_id)
    raw = _BUILDERS[spec.provider](spec, creds)
    retrying = RetryLLM(raw, retries=3, backoff_base=1.0)
    return TrackedLLM(
        retrying,
        task=task,
        org_id=org_id,
        engagement_id=engagement_id,
        provider=spec.provider,
        model=spec.model,
    )
```

- [ ] **Step 4: Run factory tests**

```bash
cd backend && python -m pytest tests/test_llm_factory.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/brain/llm_factory.py tests/test_llm_factory.py
git commit -m "feat: llm_factory with multi-provider resolution, retry, and usage tracking"
```

---

## Task 5: Add mock_llm fixture to conftest.py

**Files:**
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Add mock_llm fixture**

Append to `backend/tests/conftest.py` after the existing fixtures:

```python
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_llm(monkeypatch):
    """Patches app.brain.llm_factory.get_llm to return a single configurable AsyncMock.

    Usage in tests:
        async def test_something(mock_llm):
            mock_llm.ainvoke.return_value = MagicMock(content='{"key": "val"}')
            ...
        async def test_multi_step(mock_llm):
            mock_llm.ainvoke.side_effect = [resp1, resp2]
            ...
    """
    the_mock = AsyncMock()
    the_mock.ainvoke = AsyncMock()

    async def fake_get_llm(*args, **kw):
        return the_mock

    monkeypatch.setattr("app.brain.llm_factory.get_llm", fake_get_llm)
    return the_mock
```

- [ ] **Step 2: Verify conftest imports**

At the top of conftest.py, ensure `monkeypatch` is available (it's a built-in pytest fixture, no import needed). The `AsyncMock` and `MagicMock` imports need to be added. Add these to the top of conftest.py:

```python
from unittest.mock import AsyncMock, MagicMock
```

- [ ] **Step 3: Run to verify fixture works**

```bash
cd backend && python -m pytest tests/conftest.py --collect-only 2>&1 | grep mock_llm
```

Expected: `mock_llm` fixture appears in collection output.

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add mock_llm fixture to conftest — patches get_llm at factory level"
```

---

## Task 6: Refactor all 14 brain call sites

**Files:** (14 total)
- Modify: `backend/app/brain/agent_brain.py`
- Modify: `backend/app/brain/campaign_planner.py`
- Modify: `backend/app/brain/codebase_modeler.py`
- Modify: `backend/app/brain/evasion_strategist.py`
- Modify: `backend/app/brain/execution_judge.py`
- Modify: `backend/app/brain/exploit_engine.py`
- Modify: `backend/app/brain/exploit_script_engine.py`
- Modify: `backend/app/brain/findings_judge.py`
- Modify: `backend/app/brain/poc_engine.py`
- Modify: `backend/app/brain/semantic_modeler.py`
- Modify: `backend/app/swarm/agents/code_analyzer.py`
- Modify: `backend/app/swarm/agents/logic_modeler.py`
- Modify: `backend/app/validator/severity.py`
- Modify: `backend/app/validator/challenger.py`

The pattern for every file is:
1. Remove `from langchain_anthropic import ChatAnthropic`
2. Remove `from app.config import settings` (if only used for anthropic_api_key)
3. Remove `_LLMWrapper` class definition (and any imports of it)
4. Add `from app.brain.llm_factory import get_llm, TaskType`
5. Change `__init__` to accept `org_id=None`
6. In each async method, call `llm = await get_llm(TaskType.X, org_id=self._org_id)` instead of `self._llm.ainvoke`

- [ ] **Step 1: Update test_brain.py to use mock_llm (run first to understand breakage after refactor)**

Update `backend/tests/test_brain.py` — change all `patch.object(modeler._llm, "ainvoke", ...)` patterns:

```python
# backend/tests/test_brain.py
import pytest
from unittest.mock import MagicMock
from app.brain.semantic_modeler import SemanticModeler
from app.brain.campaign_planner import CampaignPlanner
from app.brain.evasion_strategist import EvasionStrategist
from app.brain.memory_engine import MemoryEngine


@pytest.mark.asyncio
async def test_semantic_modeler_returns_model(mock_llm):
    modeler = SemanticModeler()
    mock_llm.ainvoke.return_value = MagicMock(content='''
    {
        "app_type": "saas",
        "tech_stack": ["nodejs", "react", "postgresql"],
        "endpoints": ["/api/auth/login", "/api/users", "/api/projects"],
        "user_roles": ["admin", "member", "viewer"],
        "business_flows": ["user_registration", "project_creation", "billing"],
        "trust_boundaries": ["unauthenticated", "authenticated", "admin_only"],
        "interesting_surfaces": ["/api/auth/login", "/api/users/{id}"]
    }
    ''')
    model = await modeler.build(
        target_url="https://example.com",
        crawl_data={"paths": ["/api/auth/login", "/api/users"], "headers": {"server": "nginx"}},
    )
    assert model["app_type"] == "saas"
    assert "nodejs" in model["tech_stack"]
    assert len(model["endpoints"]) > 0


@pytest.mark.asyncio
async def test_semantic_modeler_crawl():
    modeler = SemanticModeler()
    crawl_data = await modeler.crawl("https://httpbin.org")
    assert "paths" in crawl_data
    assert "headers" in crawl_data


@pytest.mark.asyncio
async def test_campaign_planner_returns_hypotheses(mock_llm):
    planner = CampaignPlanner()
    semantic_model = {
        "app_type": "fintech",
        "tech_stack": ["nodejs", "postgresql"],
        "endpoints": ["/api/auth/login", "/api/transfer", "/api/balance"],
        "user_roles": ["user", "admin"],
        "business_flows": ["login", "fund_transfer", "balance_check"],
        "trust_boundaries": ["unauthenticated", "authenticated"],
        "interesting_surfaces": ["/api/transfer", "/api/auth/login"],
    }
    mock_llm.ainvoke.return_value = MagicMock(content='''[
        {
            "title": "Race condition in /api/transfer",
            "surface": "/api/transfer",
            "attack_class": "race_condition",
            "reasoning": "Transfer endpoint processes concurrent requests",
            "confidence": 0.85,
            "priority": "high"
        }
    ]''')
    hypotheses = await planner.generate(semantic_model, [])
    assert len(hypotheses) >= 1
    assert hypotheses[0]["attack_class"] == "race_condition"
```

(Keep any other tests in test_brain.py that don't touch LLM — just add `mock_llm` param and update the `patch.object` calls.)

- [ ] **Step 2: Update test_agent_brain.py to use mock_llm**

```python
# backend/tests/test_agent_brain.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.brain.agent_brain import AgentBrain, AgentBrainResult
from app.brain.agent_tools import AgentTool


class _EchoTool(AgentTool):
    name = "echo"
    description = "Echoes args back."
    async def execute(self, args: dict) -> str:
        return f"echo: {args}"


def _llm_resp(content: str) -> MagicMock:
    m = MagicMock()
    m.content = content
    return m


@pytest.mark.asyncio
async def test_agent_brain_stops_at_conclusion(mock_llm):
    brain = AgentBrain(system_prompt="Test agent.", tools=[_EchoTool()])
    conclusion = json.dumps({
        "conclusion": True,
        "confidence": 0.92,
        "findings": [{"vulnerability_class": "sqli", "severity": "high", "evidence": "SQL error", "description": "SQLi found"}],
        "reasoning": "Confirmed",
    })
    mock_llm.ainvoke.return_value = _llm_resp(conclusion)

    result = await brain.run({"attack_class": "sqli"}, {"target_url": "https://t.com"})

    assert isinstance(result, AgentBrainResult)
    assert result.confidence == 0.92
    assert result.steps_taken == 1
    assert len(result.findings) == 1


@pytest.mark.asyncio
async def test_agent_brain_executes_tool_then_concludes(mock_llm):
    brain = AgentBrain(system_prompt="Test agent.", tools=[_EchoTool()])
    tool_call = json.dumps({"tool": "echo", "args": {"msg": "test"}, "reasoning": "testing", "confidence": 0.4})
    conclusion = json.dumps({"conclusion": True, "confidence": 0.9, "findings": [], "reasoning": "done"})
    mock_llm.ainvoke.side_effect = [_llm_resp(tool_call), _llm_resp(conclusion)]

    result = await brain.run({}, {})

    assert result.steps_taken == 2
    assert result.confidence == 0.9
    assert mock_llm.ainvoke.call_count == 2


@pytest.mark.asyncio
async def test_agent_brain_stops_at_max_steps(mock_llm):
    brain = AgentBrain(system_prompt="Test agent.", tools=[_EchoTool()], max_steps=3)
    tool_call = json.dumps({"tool": "echo", "args": {}, "reasoning": "probing", "confidence": 0.3})
    mock_llm.ainvoke.return_value = _llm_resp(tool_call)

    result = await brain.run({}, {})

    assert result.steps_taken == 3
    assert result.confidence == 0.0
```

- [ ] **Step 3: Refactor backend/app/brain/agent_brain.py**

```python
# backend/app/brain/agent_brain.py
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage, SystemMessage

from app.brain.llm_factory import get_llm, TaskType
from app.ws import progress as ws_progress


def _truncate(s: str, n: int = 240) -> str:
    s = s if isinstance(s, str) else str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


@dataclass
class AgentBrainResult:
    findings: list[dict]
    confidence: float
    steps_taken: int
    reasoning_trace: list[dict] = field(default_factory=list)


class AgentBrain:
    """ReAct-style reasoning loop for LLM-driven agent execution."""

    def __init__(
        self,
        system_prompt: str,
        tools: list,
        confidence_threshold: float = 0.85,
        max_steps: int = 20,
        org_id=None,
    ):
        self.system_prompt = system_prompt
        self.tools: dict = {t.name: t for t in tools}
        self.confidence_threshold = confidence_threshold
        self.max_steps = max_steps
        self._org_id = org_id

    def _build_system_prompt(self) -> str:
        tool_descriptions = "\n".join(
            f"- {name}: {tool.description}"
            for name, tool in self.tools.items()
        )
        return (
            f"{self.system_prompt}\n\n"
            f"Available tools:\n{tool_descriptions}\n\n"
            "At each step, respond with ONLY valid JSON in one of these two formats:\n\n"
            "Tool call:\n"
            '{"tool": "<tool_name>", "args": {<tool-specific args>}, '
            '"reasoning": "<why this action>", "confidence": <0.0-1.0>}\n\n'
            "Conclusion (when done or confidence is high):\n"
            '{"conclusion": true, "confidence": <0.0-1.0>, '
            '"findings": [{"vulnerability_class": "<class>", "severity": "<critical|high|medium|low>", '
            '"evidence": "<observed evidence>", "description": "<details>"}], '
            '"reasoning": "<summary of what you found>"}\n\n'
            "Stop when your confidence is high or you have exhausted reasonable approaches."
        )

    async def run(
        self,
        hypothesis: dict,
        context: dict,
        engagement_id: str | None = None,
        agent_id: str | None = None,
        agent_type: str | None = None,
    ) -> AgentBrainResult:
        llm = await get_llm(TaskType.agent_brain, org_id=self._org_id)

        async def emit(phase: str, **payload) -> None:
            if not engagement_id:
                return
            await ws_progress.broadcast(engagement_id, "agent_thought", {
                "phase": phase,
                "agent_id": agent_id or "",
                "agent_type": agent_type or "",
                "step": steps,
                **payload,
            })

        messages = [
            SystemMessage(content=self._build_system_prompt()),
            HumanMessage(
                content=(
                    f"Hypothesis: {json.dumps(hypothesis)}\n"
                    f"Context: {json.dumps(context)}\n\n"
                    "Begin."
                )
            ),
        ]
        trace: list[dict] = []
        steps = 0

        while steps < self.max_steps:
            response = await llm.ainvoke(messages)
            text = response.content.strip()
            text = re.sub(r"^```json\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                steps += 1
                break

            trace.append(parsed)
            steps += 1

            reasoning = _truncate(str(parsed.get("reasoning", "")))
            confidence = float(parsed.get("confidence", 0.0))

            if parsed.get("conclusion"):
                await emit("conclusion", text=reasoning, confidence=confidence,
                           findings_count=len(parsed.get("findings", [])))
                return AgentBrainResult(
                    findings=parsed.get("findings", []),
                    confidence=confidence,
                    steps_taken=steps,
                    reasoning_trace=trace,
                )

            tool_name = parsed.get("tool", "")
            tool_args = parsed.get("args", {})

            await emit("thought", text=reasoning, tool=tool_name, confidence=confidence)

            if confidence >= self.confidence_threshold:
                return AgentBrainResult(
                    findings=[],
                    confidence=confidence,
                    steps_taken=steps,
                    reasoning_trace=trace,
                )

            tool = self.tools.get(tool_name)
            if tool is None:
                tool_result = (
                    f"Error: unknown tool '{tool_name}'. "
                    f"Available tools: {list(self.tools)}"
                )
                await emit("action", tool=tool_name, args=_truncate(json.dumps(tool_args)), error="unknown tool")
            else:
                await emit("action", tool=tool_name, args=_truncate(json.dumps(tool_args)))
                try:
                    tool_result = await tool.execute(tool_args)
                except Exception as exc:
                    tool_result = f"Tool error: {exc}"

            await emit("observation", tool=tool_name, result=_truncate(str(tool_result)))

            messages.append(response)
            messages.append(HumanMessage(content=f"Tool result:\n{tool_result}"))

        return AgentBrainResult(
            findings=[],
            confidence=0.0,
            steps_taken=steps,
            reasoning_trace=trace,
        )
```

- [ ] **Step 4: Refactor backend/app/brain/campaign_planner.py**

```python
# backend/app/brain/campaign_planner.py
import json
import re
from langchain_core.messages import HumanMessage, SystemMessage
from app.brain.llm_factory import get_llm, TaskType


SYSTEM_PROMPT = """You are a senior penetration tester generating a prioritized attack campaign.
Given a semantic model of the target application and historical knowledge base results,
generate a ranked list of attack hypotheses.

Return ONLY a valid JSON array. Each item must have:
- title: string (short hypothesis name)
- surface: string (specific endpoint or component to test)
- attack_class: string (sqli, xss, idor, auth_bypass, race_condition, business_logic, ssrf, xxe, etc.)
- reasoning: string (why this hypothesis is viable for THIS app)
- confidence: float (0.0–1.0, based on app type + KB history)
- priority: string (critical, high, medium, low)

Order by priority descending, then confidence descending. Maximum 15 hypotheses.
"""


class CampaignPlanner:
    def __init__(self, org_id=None):
        self._org_id = org_id

    async def generate(self, semantic_model: dict, kb_context: list[dict]) -> list[dict]:
        kb_summary = "\n".join(
            f"- {r.get('attack_class', '')} ({r.get('technique', '')}): {r.get('outcome', '')} hit rate {r.get('score', 0):.2f}"
            for r in kb_context[:10]
        ) or "No prior history for this target profile."

        user_content = f"""
Semantic App Model:
{json.dumps(semantic_model, indent=2)}

Relevant Knowledge Base History:
{kb_summary}
"""
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]
        llm = await get_llm(TaskType.campaign_planning, org_id=self._org_id)
        response = await llm.ainvoke(messages)
        text = response.content.strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)
```

- [ ] **Step 5: Refactor backend/app/brain/codebase_modeler.py**

Read the file fully first (`Read` tool on `backend/app/brain/codebase_modeler.py`), then replace only the LLM-related parts:
- Remove `from langchain_anthropic import ChatAnthropic`
- Remove `from app.config import settings`
- Replace the `_LLMWrapper` class definition with an import from the factory
- Change `__init__` to accept `org_id=None`
- Replace `self._llm = _LLMWrapper(ChatAnthropic(...))` with `self._org_id = org_id`
- In `model()` / any async LLM method: `llm = await get_llm(TaskType.codebase_modeling, org_id=self._org_id)` and use `llm.ainvoke(messages)`
- **Keep** `_LLMWrapper` exported as a compatibility shim that other files previously imported (findings_judge, code_analyzer). They will be refactored next, but for this step just leave a stub: remove the class entirely (findings_judge.py and code_analyzer.py will be updated in the same commit).

Key changes to `codebase_modeler.py`:
```python
# Remove these lines:
from langchain_anthropic import ChatAnthropic
from app.config import settings

# Remove the _LLMWrapper class entirely

# Add at top:
from app.brain.llm_factory import get_llm, TaskType

# Change __init__:
def __init__(self, org_id=None):
    self._org_id = org_id
    # (keep any non-LLM initialization)

# In model() or the async method that calls the LLM:
async def model(self, ...):
    llm = await get_llm(TaskType.codebase_modeling, org_id=self._org_id)
    response = await llm.ainvoke(messages)
```

- [ ] **Step 6: Refactor the remaining 9 brain/swarm/validator files**

Apply the same pattern to each file. For each:
- Remove `ChatAnthropic` import and `settings` import (if used only for api_key)
- Remove `_LLMWrapper` class and any import of it
- Add `from app.brain.llm_factory import get_llm, TaskType`
- Change `__init__` signature to accept `org_id=None`, store as `self._org_id`
- In each async method: `llm = await get_llm(TaskType.<name>, org_id=self._org_id)` then `response = await llm.ainvoke(messages)`

File-to-TaskType mapping:
| File | TaskType |
|------|----------|
| `brain/evasion_strategist.py` | `TaskType.evasion_strategist` |
| `brain/execution_judge.py` | `TaskType.execution_judge` |
| `brain/exploit_engine.py` | `TaskType.exploit_engine` |
| `brain/exploit_script_engine.py` | `TaskType.exploit_script` |
| `brain/findings_judge.py` | `TaskType.findings_judge` |
| `brain/poc_engine.py` | `TaskType.poc_engine` |
| `brain/semantic_modeler.py` | `TaskType.semantic_modeler` |
| `swarm/agents/code_analyzer.py` | `TaskType.code_analyzer` |
| `swarm/agents/logic_modeler.py` | `TaskType.logic_modeler` |
| `validator/severity.py` | `TaskType.severity_assessor` |
| `validator/challenger.py` | `TaskType.challenger` |

For `findings_judge.py`, remove `from app.brain.codebase_modeler import _LLMWrapper` (no longer needed).
For `code_analyzer.py`, remove `from app.brain.codebase_modeler import _LLMWrapper`.

For files with multiple async methods (e.g., `execution_judge.py` has `judge()` and `judge_diff()`), call `get_llm()` at the top of each method.

- [ ] **Step 7: Update test_exploit_script_engine.py to use mock_llm**

Open `backend/tests/test_exploit_script_engine.py`, add `mock_llm` parameter to each test function that patches `_llm.ainvoke`, and change `patch.object(...)` to configure `mock_llm.ainvoke.return_value` instead.

- [ ] **Step 8: Run the full test suite**

```bash
cd backend && python -m pytest tests/ -v -x 2>&1 | tail -40
```

Expected: All tests PASS. If any test fails because it still has `patch.object(modeler._llm, ...)`, find that test and update it to use `mock_llm` fixture (add `mock_llm` as a parameter and configure `mock_llm.ainvoke.return_value` instead).

- [ ] **Step 9: Commit**

```bash
git add app/brain/ app/swarm/agents/ app/validator/ tests/test_brain.py tests/test_agent_brain.py tests/test_exploit_script_engine.py
git commit -m "feat: refactor all 14 LLM call sites to use get_llm() factory"
```

---

## Task 7: Thread org_id through start.py and findings.py

**Files:**
- Modify: `backend/app/api/start.py`
- Modify: `backend/app/api/findings.py`

- [ ] **Step 1: Update start.py — pass org_id when instantiating brain objects**

In `start.py`, find each instantiation and add `org_id=engagement.org_id` (the engagement object is available in the run context):

```python
# Before:
judge = FindingsJudge()
# After:
judge = FindingsJudge(org_id=engagement.org_id)

# Before:
modeler = SemanticModeler()
# After:
modeler = SemanticModeler(org_id=engagement.org_id)

# Before:
planner = CampaignPlanner()
# After:
planner = CampaignPlanner(org_id=engagement.org_id)

# Before:
modeler = CodebaseModeler()
# After:
modeler = CodebaseModeler(org_id=engagement.org_id)

# Before:
script_engine = ExploitScriptEngine()
# After:
script_engine = ExploitScriptEngine(org_id=engagement.org_id)

# Before:
judge = ExecutionJudge()
# After:
judge = ExecutionJudge(org_id=engagement.org_id)
```

For `_judge_findings_async` which receives `engagement_id_str` but not `org_id`, update its signature to also accept `org_id` and pass it through. Find the call site where `_judge_findings_async` is called (inside start.py) and pass `org_id=engagement.org_id`.

- [ ] **Step 2: Update findings.py — pass org_id when instantiating brain objects**

In `findings.py`, the route handlers have access to the current user and can load the engagement. Pass `org_id` from the engagement:

```python
# Each route that creates an ExploitEngine/ExploitScriptEngine/ExecutionJudge:
# Load the engagement to get org_id, then:
engine = ExploitEngine(org_id=engagement.org_id)
engine = ExploitScriptEngine(org_id=engagement.org_id)
judge = ExecutionJudge(org_id=engagement.org_id)
```

For swarm agents (probe.py, recon.py, deep_exploit.py) that create `AgentBrain`, add `org_id` to the swarm agent constructors and pass it through. Read `backend/app/swarm/agents/probe.py` to see the exact instantiation and update `AgentBrain(...)` to `AgentBrain(..., org_id=self._org_id)`. Do the same for `recon.py` and `deep_exploit.py`.

- [ ] **Step 3: Run tests**

```bash
cd backend && python -m pytest tests/ -v -x 2>&1 | tail -20
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add app/api/start.py app/api/findings.py app/swarm/agents/probe.py app/swarm/agents/recon.py app/swarm/agents/deep_exploit.py
git commit -m "feat: thread org_id through brain instantiation in start.py, findings.py, swarm agents"
```

---

## Task 8: REST API for org LLM config

**Files:**
- Create: `backend/app/api/org_llm.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing API test**

Create `backend/tests/test_org_llm_endpoints.py`:

```python
# backend/tests/test_org_llm_endpoints.py
"""Tests for /api/v1/org/llm/ endpoints."""
from __future__ import annotations
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_providers_returns_four(http_client: AsyncClient):
    resp = await http_client.get("/api/v1/org/llm/providers")
    assert resp.status_code == 200
    data = resp.json()
    provider_names = {p["provider"] for p in data}
    assert provider_names == {"anthropic", "openai", "bedrock", "azure"}


@pytest.mark.asyncio
async def test_get_credentials_returns_list(http_client: AsyncClient, test_super_admin):
    resp = await http_client.get("/api/v1/org/llm/credentials")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # API key must never appear in response
    for item in data:
        assert "api_key" not in item
        assert "encrypted_key" not in item


@pytest.mark.asyncio
async def test_put_credentials_requires_admin(http_client: AsyncClient):
    resp = await http_client.put(
        "/api/v1/org/llm/credentials/anthropic",
        json={"api_key": "sk-test-key"},
    )
    assert resp.status_code in (200, 201)  # super_admin fixture is admin


@pytest.mark.asyncio
async def test_put_credentials_key_never_in_response(http_client: AsyncClient):
    resp = await http_client.put(
        "/api/v1/org/llm/credentials/openai",
        json={"api_key": "sk-openai-test"},
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert "sk-openai-test" not in str(data)


@pytest.mark.asyncio
async def test_get_task_config_returns_all_14_tasks(http_client: AsyncClient):
    resp = await http_client.get("/api/v1/org/llm/task-config")
    assert resp.status_code == 200
    data = resp.json()
    assert "tasks" in data
    assert len(data["tasks"]) == 14


@pytest.mark.asyncio
async def test_put_task_config_preset_balanced(http_client: AsyncClient):
    resp = await http_client.put(
        "/api/v1/org/llm/task-config",
        json={"preset": "balanced"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_delete_credentials(http_client: AsyncClient):
    # First create
    await http_client.put("/api/v1/org/llm/credentials/anthropic", json={"api_key": "test"})
    # Then delete
    resp = await http_client.delete("/api/v1/org/llm/credentials/anthropic")
    assert resp.status_code in (200, 204)


@pytest.mark.asyncio
async def test_audit_log_written_on_credential_set(http_client: AsyncClient, db_session):
    await http_client.put("/api/v1/org/llm/credentials/anthropic", json={"api_key": "audit-test"})
    from sqlalchemy import select
    from app.models.org_llm import OrgLLMAuditLog
    result = await db_session.execute(select(OrgLLMAuditLog))
    logs = result.scalars().all()
    assert any(log.action == "set_key" for log in logs)
```

- [ ] **Step 2: Run to verify fails**

```bash
cd backend && python -m pytest tests/test_org_llm_endpoints.py::test_get_providers_returns_four -v
```

Expected: `404 Not Found` (route doesn't exist yet).

- [ ] **Step 3: Create backend/app/api/org_llm.py**

```python
# backend/app/api/org_llm.py
"""REST API for per-org LLM provider configuration.

All write endpoints require admin role. Keys are never returned in responses.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_admin
from app.brain.llm_factory import (
    DEFAULT_TASK_SPECS, Provider, TaskType, _fernet, _ENV_CREDS,
    _SMART_MODELS, _CHEAP_MODELS,
)
from app.database import get_db
from app.models.org_llm import OrgLLMCredential, OrgLLMTaskConfig, OrgLLMAuditLog
from app.models.user import User

router = APIRouter(prefix="/api/v1/org/llm", tags=["org-llm"])

# ── Request / Response schemas ────────────────────────────────────────────────

class CredentialStatus(BaseModel):
    provider: str
    configured: bool
    use_iam_role: bool = False
    region: str | None = None
    endpoint: str | None = None
    last_tested_at: datetime | None = None


class UpsertCredentialRequest(BaseModel):
    api_key: str | None = None
    region: str | None = None
    endpoint: str | None = None
    use_iam_role: bool = False


class TaskConfigEntry(BaseModel):
    provider: str
    model: str
    max_tokens: int
    temperature: float = 0.0
    from_default: bool = True


class TaskConfigResponse(BaseModel):
    preset: str
    tasks: dict[str, TaskConfigEntry]


class SetPresetRequest(BaseModel):
    preset: Literal["smart", "balanced", "cheap"]


class SetCustomRequest(BaseModel):
    custom: dict[str, dict]  # task_type → {provider, model, max_tokens}


class TestResult(BaseModel):
    ok: bool
    error: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _encrypt_key(api_key: str) -> bytes:
    if _fernet is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="FORGE_SECRETS_KEY is not configured — cannot store credentials securely.",
        )
    return _fernet.encrypt(api_key.encode())


async def _write_audit(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    action: str,
    payload: dict,
) -> None:
    log = OrgLLMAuditLog(org_id=org_id, user_id=user_id, action=action, payload=payload)
    db.add(log)


def _detect_preset(org_id: uuid.UUID, rows: list[OrgLLMTaskConfig]) -> str:
    if not rows:
        return "balanced"
    by_task = {r.task_type: r for r in rows}
    if len(by_task) < len(TaskType):
        return "custom"
    provider = Provider(list(by_task.values())[0].provider)
    smart = _SMART_MODELS.get(provider)
    cheap = _CHEAP_MODELS.get(provider)
    if all(r.model == smart for r in by_task.values()):
        return "smart"
    if all(r.model == cheap for r in by_task.values()):
        return "cheap"
    return "custom"


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/providers", response_model=list[dict])
async def list_providers():
    """List supported providers and their required fields."""
    return [
        {"provider": "anthropic", "required_fields": ["api_key"]},
        {"provider": "openai", "required_fields": ["api_key"]},
        {"provider": "bedrock", "required_fields": [], "optional_fields": ["api_key", "region", "use_iam_role"]},
        {"provider": "azure", "required_fields": ["api_key", "endpoint"]},
    ]


@router.get("/credentials", response_model=list[CredentialStatus])
async def list_credentials(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List configured providers for the org. Never returns the actual key."""
    if user.org_id is None:
        return []
    result = await db.execute(
        select(OrgLLMCredential).where(OrgLLMCredential.org_id == user.org_id)
    )
    rows = {r.provider: r for r in result.scalars().all()}
    out = []
    for p in Provider:
        row = rows.get(p.value)
        if row:
            out.append(CredentialStatus(
                provider=p.value,
                configured=True,
                use_iam_role=row.extra.get("use_iam_role", False),
                region=row.region,
                endpoint=row.endpoint,
                last_tested_at=row.last_tested_at,
            ))
        else:
            out.append(CredentialStatus(provider=p.value, configured=False))
    return out


@router.put("/credentials/{provider}", status_code=status.HTTP_200_OK)
async def upsert_credential(
    provider: str,
    body: UpsertCredentialRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Store (or replace) credentials for a provider. Key is encrypted before storage."""
    try:
        prov = Provider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    if user.org_id is None:
        raise HTTPException(status_code=400, detail="User has no org")

    result = await db.execute(
        select(OrgLLMCredential).where(
            OrgLLMCredential.org_id == user.org_id,
            OrgLLMCredential.provider == prov.value,
        )
    )
    row = result.scalar_one_or_none()

    encrypted = _encrypt_key(body.api_key) if body.api_key else None
    extra = {"use_iam_role": body.use_iam_role}

    if row:
        row.encrypted_key = encrypted
        row.region = body.region
        row.endpoint = body.endpoint
        row.extra = extra
        row.updated_at = datetime.utcnow()
    else:
        row = OrgLLMCredential(
            org_id=user.org_id,
            provider=prov.value,
            encrypted_key=encrypted,
            region=body.region,
            endpoint=body.endpoint,
            extra=extra,
        )
        db.add(row)

    await _write_audit(db, user.org_id, user.id, "set_key", {"provider": provider})
    return {"status": "ok", "provider": provider}


@router.post("/credentials/{provider}/test", response_model=TestResult)
async def test_credential(
    provider: str,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Probe the provider with a 1-token request to validate credentials."""
    try:
        prov = Provider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    from app.brain.llm_factory import _resolve_credentials, _BUILDERS, LLMSpec
    from langchain_core.messages import HumanMessage

    try:
        creds = await _resolve_credentials(prov, user.org_id)
        spec = LLMSpec(provider=prov, model=DEFAULT_TASK_SPECS[TaskType.challenger].model, max_tokens=1)
        raw_llm = _BUILDERS[prov](spec, creds)
        await raw_llm.ainvoke([HumanMessage(content="hi")])

        # Mark last tested
        result = await db.execute(
            select(OrgLLMCredential).where(
                OrgLLMCredential.org_id == user.org_id,
                OrgLLMCredential.provider == prov.value,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.last_tested_at = datetime.utcnow()

        await _write_audit(db, user.org_id, user.id, "test", {"provider": provider, "ok": True})
        return TestResult(ok=True)
    except Exception as e:
        await _write_audit(db, user.org_id, user.id, "test", {"provider": provider, "ok": False, "error": str(e)})
        return TestResult(ok=False, error=str(e))


@router.delete("/credentials/{provider}", status_code=status.HTTP_200_OK)
async def revoke_credential(
    provider: str,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete stored credentials for a provider."""
    try:
        prov = Provider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    if user.org_id is None:
        raise HTTPException(status_code=400, detail="User has no org")

    result = await db.execute(
        select(OrgLLMCredential).where(
            OrgLLMCredential.org_id == user.org_id,
            OrgLLMCredential.provider == prov.value,
        )
    )
    row = result.scalar_one_or_none()
    if row:
        await db.delete(row)
    await _write_audit(db, user.org_id, user.id, "revoke", {"provider": provider})
    return {"status": "ok"}


@router.get("/task-config", response_model=TaskConfigResponse)
async def get_task_config(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the full TaskType → LLMSpec mapping for this org (defaults filled in)."""
    org_overrides: dict[str, OrgLLMTaskConfig] = {}
    if user.org_id:
        result = await db.execute(
            select(OrgLLMTaskConfig).where(OrgLLMTaskConfig.org_id == user.org_id)
        )
        org_overrides = {r.task_type: r for r in result.scalars().all()}

    tasks: dict[str, TaskConfigEntry] = {}
    for task in TaskType:
        row = org_overrides.get(task.value)
        if row:
            tasks[task.value] = TaskConfigEntry(
                provider=row.provider,
                model=row.model,
                max_tokens=row.max_tokens or DEFAULT_TASK_SPECS[task].max_tokens,
                temperature=row.temperature or 0.0,
                from_default=False,
            )
        else:
            spec = DEFAULT_TASK_SPECS[task]
            tasks[task.value] = TaskConfigEntry(
                provider=spec.provider.value,
                model=spec.model,
                max_tokens=spec.max_tokens,
                temperature=spec.temperature,
                from_default=True,
            )

    preset = _detect_preset(user.org_id, list(org_overrides.values())) if user.org_id else "balanced"
    return TaskConfigResponse(preset=preset, tasks=tasks)


@router.put("/task-config", status_code=status.HTTP_200_OK)
async def set_task_config(
    body: dict,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Apply a preset (smart/balanced/cheap) or set custom per-task config."""
    if user.org_id is None:
        raise HTTPException(status_code=400, detail="User has no org")

    # Determine what to write
    configs: dict[str, dict] = {}

    if "preset" in body:
        preset = body["preset"]
        if preset not in ("smart", "balanced", "cheap"):
            raise HTTPException(status_code=400, detail="preset must be smart, balanced, or cheap")

        # Get org's primary provider (use anthropic if none configured)
        cred_result = await db.execute(
            select(OrgLLMCredential).where(OrgLLMCredential.org_id == user.org_id)
        )
        cred_rows = cred_result.scalars().all()
        provider = Provider(cred_rows[0].provider) if cred_rows else Provider.anthropic

        for task in TaskType:
            if preset == "smart":
                model = _SMART_MODELS[provider]
            elif preset == "cheap":
                model = _CHEAP_MODELS[provider]
            else:  # balanced
                default = DEFAULT_TASK_SPECS[task]
                model = default.model
                provider = default.provider
            configs[task.value] = {
                "provider": provider.value,
                "model": model,
                "max_tokens": DEFAULT_TASK_SPECS[task].max_tokens,
            }
        await _write_audit(db, user.org_id, user.id, "apply_preset", {"preset": preset})

    elif "custom" in body:
        configs = body["custom"]
        await _write_audit(db, user.org_id, user.id, "set_task_config", {"tasks": list(configs.keys())})
    else:
        raise HTTPException(status_code=400, detail="body must contain 'preset' or 'custom'")

    # Upsert rows
    for task_type, cfg in configs.items():
        result = await db.execute(
            select(OrgLLMTaskConfig).where(
                OrgLLMTaskConfig.org_id == user.org_id,
                OrgLLMTaskConfig.task_type == task_type,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.provider = cfg["provider"]
            row.model = cfg["model"]
            row.max_tokens = cfg.get("max_tokens")
            row.updated_at = datetime.utcnow()
        else:
            db.add(OrgLLMTaskConfig(
                org_id=user.org_id,
                task_type=task_type,
                provider=cfg["provider"],
                model=cfg["model"],
                max_tokens=cfg.get("max_tokens"),
            ))

    return {"status": "ok"}


@router.get("/audit")
async def get_audit_log(
    limit: int = 100,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return recent audit log entries for this org."""
    if user.org_id is None:
        return []
    result = await db.execute(
        select(OrgLLMAuditLog)
        .where(OrgLLMAuditLog.org_id == user.org_id)
        .order_by(OrgLLMAuditLog.created_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "user_id": str(r.user_id) if r.user_id else None,
            "action": r.action,
            "payload": r.payload,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/usage")
async def get_usage(
    since: str | None = None,
    group_by: str = "task",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregated LLM usage for this org."""
    from sqlalchemy import func
    from app.models.llm_usage import LLMUsageEvent

    if user.org_id is None:
        return []

    query = select(
        LLMUsageEvent.task,
        LLMUsageEvent.provider,
        LLMUsageEvent.model,
        func.sum(LLMUsageEvent.input_tokens).label("input_tokens"),
        func.sum(LLMUsageEvent.output_tokens).label("output_tokens"),
        func.sum(LLMUsageEvent.cost_usd).label("cost_usd"),
        func.count().label("calls"),
    ).where(LLMUsageEvent.org_id == user.org_id)

    if since:
        from datetime import datetime as dt
        try:
            since_dt = dt.fromisoformat(since.replace("Z", "+00:00"))
            query = query.where(LLMUsageEvent.created_at >= since_dt)
        except ValueError:
            pass

    query = query.group_by(LLMUsageEvent.task, LLMUsageEvent.provider, LLMUsageEvent.model)
    result = await db.execute(query)
    rows = result.all()
    return [
        {
            "task": r.task,
            "provider": r.provider,
            "model": r.model,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cost_usd": float(r.cost_usd or 0),
            "calls": r.calls,
        }
        for r in rows
    ]
```

- [ ] **Step 4: Register router in main.py**

In `backend/app/main.py`, add after the existing router imports:

```python
from app.api.org_llm import router as org_llm_router
```

And after the last `app.include_router(...)` line:

```python
app.include_router(org_llm_router)
```

- [ ] **Step 5: Update conftest.py to import new models**

In `backend/tests/conftest.py`, update the model import line:

```python
# OLD:
from app.models import engagement, agent, task, finding, knowledge, user, api_key, organization  # noqa: F401

# NEW:
from app.models import engagement, agent, task, finding, knowledge, user, api_key, organization, org_llm, llm_usage  # noqa: F401
```

- [ ] **Step 6: Run API tests**

```bash
cd backend && python -m pytest tests/test_org_llm_endpoints.py -v
```

Expected: All tests PASS.

- [ ] **Step 7: Run full suite**

```bash
cd backend && python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: All tests PASS.

- [ ] **Step 8: Commit**

```bash
git add app/api/org_llm.py app/main.py tests/test_org_llm_endpoints.py tests/conftest.py
git commit -m "feat: REST API for org LLM credentials, task config, audit log, and usage"
```

---

## Task 9: CLI commands for org llm

**Files:**
- Create: `backend/cli/forge_cli/commands/org_llm.py`
- Modify: `backend/cli/forge_cli/main.py`

- [ ] **Step 1: Create backend/cli/forge_cli/commands/org_llm.py**

```python
# backend/cli/forge_cli/commands/org_llm.py
"""CLI commands: forge org llm <subcommand>"""
from __future__ import annotations
import getpass

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from forge_cli.api import ForgeClient, APIError, _load_config

console = Console()


def _get_client(ctx) -> ForgeClient:
    config = _load_config()
    import os
    api_url = ctx.obj.get("api_url") or config.get("api_url") or os.environ.get("FORGE_API_URL", "http://localhost:8080")
    return ForgeClient(api_url)


@click.group("llm")
@click.pass_context
def llm_group(ctx):
    """Manage AI provider configuration for your org."""
    ctx.ensure_object(dict)


@llm_group.command("show")
@click.pass_context
def llm_show(ctx):
    """Display current provider credentials and task configuration."""
    client = _get_client(ctx)
    try:
        creds = client.get("/api/v1/org/llm/credentials")
        config = client.get("/api/v1/org/llm/task-config")
    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)

    # Credentials panel
    cred_lines = []
    for c in creds:
        status = "✓ configured" if c["configured"] else "✗ not configured"
        extra = ""
        if c.get("use_iam_role"):
            extra = f" · IAM role · {c.get('region', '')}"
        elif c.get("last_tested_at"):
            extra = f" · last tested {c['last_tested_at'][:10]}"
        cred_lines.append(f"  {c['provider']:<12} {status}{extra}")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Task")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Max Tokens")
    table.add_column("Source")

    for task_name, entry in config.get("tasks", {}).items():
        source = "[dim]default[/dim]" if entry.get("from_default") else "[green]org override[/green]"
        table.add_row(task_name, entry["provider"], entry["model"], str(entry["max_tokens"]), source)

    console.print(Panel(
        "\n".join([
            "[bold]Active credentials[/bold]",
            *cred_lines,
            "",
            f"[bold]Preset:[/bold] {config.get('preset', 'balanced')}",
        ]),
        title="AI Provider Configuration",
    ))
    console.print(table)


@llm_group.command("preset")
@click.argument("preset_name", type=click.Choice(["smart", "balanced", "cheap"]))
@click.pass_context
def llm_preset(ctx, preset_name: str):
    """Apply a model preset: smart | balanced | cheap."""
    client = _get_client(ctx)
    try:
        client.put("/api/v1/org/llm/task-config", json={"preset": preset_name})
        console.print(f"[green]✓[/green] Applied preset: {preset_name}")
    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@llm_group.command("set")
@click.argument("task_type")
@click.option("--provider", required=True, help="Provider: anthropic|openai|bedrock|azure")
@click.option("--model", required=True, help="Model identifier")
@click.option("--max-tokens", type=int, default=None)
@click.pass_context
def llm_set(ctx, task_type: str, provider: str, model: str, max_tokens: int | None):
    """Set provider/model for a specific task type."""
    client = _get_client(ctx)
    cfg: dict = {"provider": provider, "model": model}
    if max_tokens:
        cfg["max_tokens"] = max_tokens
    try:
        client.put("/api/v1/org/llm/task-config", json={"custom": {task_type: cfg}})
        console.print(f"[green]✓[/green] {task_type} → {provider}/{model}")
    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@click.group("key")
def key_group():
    """Manage provider API keys."""


@key_group.command("set")
@click.argument("provider")
@click.option("--iam-role", is_flag=True, help="Use IAM role for Bedrock (no key needed)")
@click.option("--region", default=None)
@click.option("--endpoint", default=None)
@click.pass_context
def key_set(ctx, provider: str, iam_role: bool, region: str | None, endpoint: str | None):
    """Set API key for a provider (prompts securely; key is never echoed)."""
    client = _get_client(ctx)
    body: dict = {"use_iam_role": iam_role, "region": region, "endpoint": endpoint}
    if not iam_role:
        key = getpass.getpass(f"Enter {provider} API key: ")
        body["api_key"] = key
    try:
        client.put(f"/api/v1/org/llm/credentials/{provider}", json=body)
        console.print(f"[green]✓[/green] {provider} credentials saved")
    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@key_group.command("test")
@click.argument("provider")
@click.pass_context
def key_test(ctx, provider: str):
    """Validate credentials by sending a 1-token probe to the provider."""
    client = _get_client(ctx)
    try:
        result = client.post(f"/api/v1/org/llm/credentials/{provider}/test", json={})
        if result.get("ok"):
            console.print(f"[green]✓[/green] {provider} credentials valid")
        else:
            console.print(f"[red]✗[/red] {provider} test failed: {result.get('error')}")
            raise SystemExit(1)
    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@key_group.command("revoke")
@click.argument("provider")
@click.pass_context
def key_revoke(ctx, provider: str):
    """Delete stored credentials for a provider."""
    client = _get_client(ctx)
    try:
        client.delete(f"/api/v1/org/llm/credentials/{provider}")
        console.print(f"[green]✓[/green] {provider} credentials revoked")
    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)


@llm_group.command("usage")
@click.option("--since", default=None, help="ISO date, e.g. 2026-05-01")
@click.option("--by", "group_by", default="task", type=click.Choice(["task", "engagement", "day"]))
@click.pass_context
def llm_usage(ctx, since: str | None, group_by: str):
    """Show LLM usage and cost breakdown."""
    client = _get_client(ctx)
    params = {}
    if since:
        params["since"] = since
    params["group_by"] = group_by
    try:
        rows = client.get("/api/v1/org/llm/usage", params=params)
    except APIError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Task")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Calls", justify="right")
    table.add_column("Input tokens", justify="right")
    table.add_column("Output tokens", justify="right")
    table.add_column("Cost (USD)", justify="right")
    for r in rows:
        table.add_row(
            r["task"], r["provider"], r["model"],
            str(r["calls"]), str(r["input_tokens"]), str(r["output_tokens"]),
            f"${r['cost_usd']:.4f}",
        )
    console.print(table)


llm_group.add_command(key_group)
```

- [ ] **Step 2: Update cli/forge_cli/main.py to add org llm group**

First, read `backend/cli/forge_cli/main.py` (it currently ends with `cli.add_command(ci_group)`).

Add after the last `cli.add_command(...)` line:

```python
from forge_cli.commands.org_llm import llm_group

@cli.group("org")
def org_group():
    """Org-level configuration commands."""

org_group.add_command(llm_group)
cli.add_command(org_group)
```

- [ ] **Step 3: Verify CLI loads without error**

```bash
cd cli && python -m forge_cli.main org llm --help
```

Expected: Help text showing `show`, `preset`, `set`, `key`, `usage` subcommands.

- [ ] **Step 4: Commit**

```bash
git add cli/forge_cli/commands/org_llm.py cli/forge_cli/main.py
git commit -m "feat: CLI commands for forge org llm (show, preset, set, key, usage)"
```

---

## Task 10: UUID portability — swap all models to use SQLAlchemy Uuid

**Files:**
- Modify: `backend/app/models/organization.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/engagement.py`
- Modify: `backend/app/models/task.py`
- Modify: `backend/app/models/finding.py`
- Modify: `backend/app/models/agent.py`
- Modify: `backend/app/models/api_key.py`
- Modify: `backend/app/models/knowledge.py`

The change in every file is identical. For each file:

- [ ] **Step 1: Write portability test**

Add to `backend/tests/test_models.py`:

```python
def test_no_postgres_uuid_dialect():
    """All models must use portable sqlalchemy.Uuid, not dialects.postgresql.UUID."""
    import importlib, inspect, pkgutil
    import app.models as models_pkg
    for _, mod_name, _ in pkgutil.iter_modules(models_pkg.__path__):
        mod = importlib.import_module(f"app.models.{mod_name}")
        source = inspect.getsource(mod)
        assert "dialects.postgresql" not in source, (
            f"app/models/{mod_name}.py imports from dialects.postgresql — "
            "use 'from sqlalchemy import Uuid' instead"
        )
```

- [ ] **Step 2: Run to verify fails**

```bash
cd backend && python -m pytest tests/test_models.py::test_no_postgres_uuid_dialect -v
```

Expected: FAIL — most model files import from `sqlalchemy.dialects.postgresql`.

- [ ] **Step 3: Update organization.py**

```python
# backend/app/models/organization.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 4: Update user.py**

Read the file first with Read tool. Make the same swap:
- Remove `from sqlalchemy.dialects.postgresql import UUID`
- Add `Uuid` to the `from sqlalchemy import ...` line
- Replace every `UUID(as_uuid=True)` with `Uuid`

- [ ] **Step 5: Update engagement.py, task.py, finding.py, agent.py, api_key.py, knowledge.py**

Apply the same swap in each file. Pattern:
```python
# OLD import line:
from sqlalchemy.dialects.postgresql import UUID

# NEW: add Uuid to existing sqlalchemy import
from sqlalchemy import ..., Uuid

# OLD column:
id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

# NEW:
id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
```

Apply to ALL UUID columns in each file (primary keys and foreign keys).

- [ ] **Step 6: Run portability test**

```bash
cd backend && python -m pytest tests/test_models.py::test_no_postgres_uuid_dialect -v
```

Expected: PASS.

- [ ] **Step 7: Run full test suite**

```bash
cd backend && python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: All tests PASS. (The test DB is Postgres so `Uuid` renders the same as before — existing tests should be unaffected.)

- [ ] **Step 8: Add asyncmy to requirements (MySQL support)**

In `backend/requirements.txt`, verify `asyncmy==0.2.10` is present (added in Task 1). No code changes needed — `DB_URL` drives dialect selection in SQLAlchemy automatically.

- [ ] **Step 9: Commit**

```bash
git add app/models/
git commit -m "feat: swap all UUID columns to portable sqlalchemy.Uuid (Postgres + MySQL compatible)"
```

---

## Task 11: Final verification — run full test suite

- [ ] **Step 1: Run all tests**

```bash
cd backend && python -m pytest tests/ -v --tb=short 2>&1
```

Expected: All tests PASS. Zero failures.

- [ ] **Step 2: Verify no remaining ChatAnthropic imports in app code**

```bash
grep -rn "ChatAnthropic\|from langchain_anthropic" /path/to/backend/app/ --include="*.py"
```

Expected: Zero results (all call sites have been refactored).

- [ ] **Step 3: Verify no remaining dialects.postgresql imports in models**

```bash
grep -rn "dialects.postgresql" /path/to/backend/app/models/ --include="*.py"
```

Expected: Zero results.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: final cleanup after multi-provider LLM + portable DB implementation"
```

---

## Self-Review: Spec Coverage Check

| Spec requirement | Task |
|-----------------|------|
| Per-org LLM provider selection | Task 4 (_resolve_spec, _resolve_credentials) |
| Encrypted key storage (Fernet) | Task 4 (_fernet, _encrypt_key) + Task 8 (PUT /credentials) |
| 4 providers: Anthropic, OpenAI, Bedrock, Azure | Task 4 (_BUILDERS dict) |
| DEFAULT_TASK_SPECS (14 task types) | Task 4 |
| Presets: Smart / Balanced / Cheap | Task 8 (PUT /task-config) |
| Fallback to env vars | Task 4 (_ENV_CREDS) |
| Exponential backoff (3 retries) | Task 4 (RetryLLM) |
| Usage tracking (TrackedLLM) | Task 4 (TrackedLLM, _log_usage) |
| Pricing table | Task 4 (_PRICING, _price) |
| 4 new DB tables | Task 2 (models) + Task 3 (migration) |
| MySQL portability (Uuid swap) | Task 10 |
| asyncmy driver | Task 1 |
| REST endpoints (GET providers, GET/PUT/DELETE credentials, POST test, GET/PUT task-config, GET usage, GET audit) | Task 8 |
| Key never returned in responses | Task 8 (CredentialStatus schema) |
| Audit log on every write | Task 8 (_write_audit) |
| CLI: forge org llm show/preset/set/key/usage | Task 9 |
| mock_llm fixture for tests | Task 5 |
| Refactor all 14 call sites | Task 6 |
| Thread org_id through start.py/findings.py | Task 7 |
| test_llm_factory.py | Task 4 |
| test_org_llm_endpoints.py | Task 8 |
| FORGE_SECRETS_KEY env var | Task 1 (config) + Task 4 (factory) |
| Backend warning if no keys configured | Task 4 (_fernet init warning) |
