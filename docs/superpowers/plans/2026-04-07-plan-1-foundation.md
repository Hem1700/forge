# FORGE Plan 1: Foundation & Infrastructure

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the full local development environment — Docker services, PostgreSQL models, Alembic migrations, config, and a working FastAPI skeleton with a health endpoint.

**Architecture:** PostgreSQL for engagement/finding persistence, Redis for task board messaging, Qdrant for vector search, Neo4j for graph reasoning. All services run via Docker Compose. FastAPI backend uses SQLAlchemy async ORM with Alembic migrations. Config via pydantic-settings with `.env` override.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x (async), Alembic, pydantic-settings, asyncpg, Docker Compose, pytest-asyncio

---

## File Map

| File | Purpose |
|---|---|
| `docker-compose.yml` | PostgreSQL, Redis, Qdrant, Neo4j services |
| `Makefile` | dev shortcuts (up, down, migrate, test) |
| `backend/.env.example` | env var template |
| `backend/requirements.txt` | all Python deps |
| `backend/app/config.py` | pydantic-settings config singleton |
| `backend/app/database.py` | async SQLAlchemy engine + session factory + Base |
| `backend/app/main.py` | FastAPI app, router registration, lifespan |
| `backend/app/models/engagement.py` | Engagement ORM model |
| `backend/app/models/agent.py` | Agent ORM model |
| `backend/app/models/task.py` | Task + Bid ORM models |
| `backend/app/models/finding.py` | Finding + Evidence ORM models |
| `backend/app/models/knowledge.py` | KnowledgeGraphEntry ORM model |
| `backend/alembic.ini` | Alembic config |
| `backend/alembic/env.py` | Alembic async env |
| `backend/alembic/versions/0001_initial.py` | initial migration |
| `backend/tests/conftest.py` | pytest fixtures (async DB session, test client) |
| `backend/tests/test_health.py` | health endpoint test |

---

### Task 1: Docker Compose + Makefile

**Files:**
- Create: `docker-compose.yml`
- Create: `Makefile`

- [ ] **Step 1: Write docker-compose.yml**

```yaml
# docker-compose.yml
version: "3.9"

services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: forge
      POSTGRES_PASSWORD: forge
      POSTGRES_DB: forge
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U forge"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage

  neo4j:
    image: neo4j:5
    environment:
      NEO4J_AUTH: neo4j/forge_password
      NEO4J_PLUGINS: '["apoc"]'
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - neo4j_data:/data
    healthcheck:
      test: ["CMD", "neo4j", "status"]
      interval: 10s
      timeout: 10s
      retries: 10

volumes:
  postgres_data:
  qdrant_data:
  neo4j_data:
```

- [ ] **Step 2: Write Makefile**

```makefile
# Makefile
.PHONY: up down logs migrate test shell

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	cd backend && alembic upgrade head

test:
	cd backend && pytest -v

shell:
	cd backend && python -m ipython

dev:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- [ ] **Step 3: Start services and verify**

```bash
make up
docker compose ps
# Expected: postgres, redis, qdrant, neo4j all showing "healthy" or "running"
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml Makefile
git commit -m "feat: add docker-compose and Makefile for local dev stack"
```

---

### Task 2: Python Project Setup

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py`

- [ ] **Step 1: Write requirements.txt**

```text
# backend/requirements.txt
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy[asyncio]==2.0.35
asyncpg==0.29.0
alembic==1.13.3
pydantic-settings==2.5.2
pydantic==2.9.2
redis[hiredis]==5.1.1
qdrant-client==1.11.3
neo4j==5.25.0
anthropic==0.37.1
langchain==0.3.7
langchain-anthropic==0.2.4
langgraph==0.2.38
httpx==0.27.2
playwright==1.47.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.12
structlog==24.4.0

# dev/test
pytest==8.3.3
pytest-asyncio==0.24.0
pytest-cov==5.0.0
httpx==0.27.2
```

- [ ] **Step 2: Write .env.example**

```bash
# backend/.env.example
DATABASE_URL=postgresql+asyncpg://forge:forge@localhost:5432/forge
REDIS_URL=redis://localhost:6379
QDRANT_URL=http://localhost:6333
NEO4J_URL=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=forge_password
ANTHROPIC_API_KEY=your-key-here
USE_LOCAL_LLM=false
OLLAMA_URL=http://localhost:11434
JWT_SECRET=change-me-in-production
CONFIDENCE_THRESHOLD=0.75
THREAD_DEATH_THRESHOLD=5
```

- [ ] **Step 3: Install dependencies**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 4: Create app package**

```bash
touch backend/app/__init__.py
touch backend/app/models/__init__.py
touch backend/app/api/__init__.py
touch backend/app/brain/__init__.py
touch backend/app/swarm/__init__.py
touch backend/app/swarm/agents/__init__.py
touch backend/app/validator/__init__.py
touch backend/app/knowledge/__init__.py
touch backend/app/ws/__init__.py
```

- [ ] **Step 5: Commit**

```bash
git add backend/
git commit -m "feat: python project setup, requirements, env template"
```

---

### Task 3: Config + Database

**Files:**
- Create: `backend/app/config.py`
- Create: `backend/app/database.py`

- [ ] **Step 1: Write test for config**

```python
# backend/tests/test_config.py
from app.config import settings

def test_settings_has_required_fields():
    assert settings.database_url.startswith("postgresql")
    assert settings.redis_url.startswith("redis")
    assert settings.confidence_threshold == 0.75
    assert settings.thread_death_threshold == 5
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd backend && pytest tests/test_config.py -v
# Expected: ModuleNotFoundError: No module named 'app.config'
```

- [ ] **Step 3: Write config.py**

```python
# backend/app/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://forge:forge@localhost:5432/forge"
    redis_url: str = "redis://localhost:6379"
    qdrant_url: str = "http://localhost:6333"
    neo4j_url: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "forge_password"
    anthropic_api_key: str = ""
    use_local_llm: bool = False
    ollama_url: str = "http://localhost:11434"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    confidence_threshold: float = 0.75
    thread_death_threshold: int = 5

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 4: Write database.py**

```python
# backend/app/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

- [ ] **Step 5: Run test — verify it passes**

```bash
cd backend && pytest tests/test_config.py -v
# Expected: PASSED
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/app/database.py backend/tests/test_config.py
git commit -m "feat: config and async database setup"
```

---

### Task 4: ORM Models

**Files:**
- Create: `backend/app/models/engagement.py`
- Create: `backend/app/models/agent.py`
- Create: `backend/app/models/task.py`
- Create: `backend/app/models/finding.py`
- Create: `backend/app/models/knowledge.py`

- [ ] **Step 1: Write models test**

```python
# backend/tests/test_models.py
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
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd backend && pytest tests/test_models.py -v
# Expected: ImportError
```

- [ ] **Step 3: Write engagement.py**

```python
# backend/app/models/engagement.py
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, DateTime, JSON, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class EngagementStatus(str, PyEnum):
    pending = "pending"
    running = "running"
    paused_at_gate = "paused_at_gate"
    complete = "complete"
    aborted = "aborted"


class GateStatus(str, PyEnum):
    gate_1 = "gate_1"
    gate_2 = "gate_2"
    gate_3 = "gate_3"
    complete = "complete"


class Engagement(Base):
    __tablename__ = "engagements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_url: Mapped[str] = mapped_column(String, nullable=False)
    target_scope: Mapped[list] = mapped_column(JSON, default=list)
    target_out_of_scope: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[EngagementStatus] = mapped_column(SAEnum(EngagementStatus), default=EngagementStatus.pending)
    gate_status: Mapped[GateStatus] = mapped_column(SAEnum(GateStatus), default=GateStatus.gate_1)
    semantic_model: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 4: Write agent.py**

```python
# backend/app/models/agent.py
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, DateTime, JSON, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class AgentType(str, PyEnum):
    recon = "recon"
    logic_modeler = "logic_modeler"
    probe = "probe"
    evasion = "evasion"
    deep_exploit = "deep_exploit"
    child = "child"
    validator = "validator"


class AgentStatus(str, PyEnum):
    idle = "idle"
    bidding = "bidding"
    running = "running"
    terminated = "terminated"
    completed = "completed"


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engagements.id"), nullable=False)
    type: Mapped[AgentType] = mapped_column(SAEnum(AgentType), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    spawned_reason: Mapped[str] = mapped_column(String, default="")
    status: Mapped[AgentStatus] = mapped_column(SAEnum(AgentStatus), default=AgentStatus.idle)
    current_task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    signal_history: Mapped[list] = mapped_column(JSON, default=list)
    termination_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    tools: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 5: Write task.py**

```python
# backend/app/models/task.py
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, DateTime, JSON, Enum as SAEnum, ForeignKey, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Priority(str, PyEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class TaskStatus(str, PyEnum):
    open = "open"
    bidding = "bidding"
    assigned = "assigned"
    awaiting_human_gate = "awaiting_human_gate"
    complete = "complete"
    rejected = "rejected"


class NoiseLevel(str, PyEnum):
    low = "low"
    medium = "medium"
    high = "high"


class BidOutcome(str, PyEnum):
    won = "won"
    lost = "lost"
    expired = "expired"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engagements.id"), nullable=False)
    hypothesis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    surface: Mapped[str] = mapped_column(String, nullable=False)
    required_confidence: Mapped[float] = mapped_column(Float, default=0.6)
    priority: Mapped[Priority] = mapped_column(SAEnum(Priority), default=Priority.medium)
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), default=TaskStatus.open)
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    event_log: Mapped[list] = mapped_column(JSON, default=list)


class Bid(Base):
    __tablename__ = "bids"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    basis: Mapped[str] = mapped_column(String, default="")
    estimated_probes: Mapped[int] = mapped_column(Integer, default=1)
    noise_level: Mapped[NoiseLevel] = mapped_column(SAEnum(NoiseLevel), default=NoiseLevel.medium)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    outcome: Mapped[BidOutcome | None] = mapped_column(SAEnum(BidOutcome), nullable=True)
```

- [ ] **Step 6: Write finding.py**

```python
# backend/app/models/finding.py
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, DateTime, JSON, Enum as SAEnum, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Severity(str, PyEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class ValidationStatus(str, PyEnum):
    pending = "pending"
    validated = "validated"
    rejected = "rejected"


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engagements.id"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    vulnerability_class: Mapped[str] = mapped_column(String, nullable=False)
    affected_surface: Mapped[str] = mapped_column(String, nullable=False)
    reproduction_steps: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    cvss_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[Severity] = mapped_column(SAEnum(Severity), default=Severity.medium)
    validation_status: Mapped[ValidationStatus] = mapped_column(SAEnum(ValidationStatus), default=ValidationStatus.pending)
    validation_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 7: Write knowledge.py**

```python
# backend/app/models/knowledge.py
import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, DateTime, JSON, Enum as SAEnum, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class OutcomeType(str, PyEnum):
    confirmed = "confirmed"
    false_positive = "false_positive"
    inconclusive = "inconclusive"


class KnowledgeGraphEntry(Base):
    __tablename__ = "knowledge_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engagements.id"), nullable=False)
    tech_stack: Mapped[list] = mapped_column(JSON, default=list)
    app_type: Mapped[str] = mapped_column(String, default="")
    attack_class: Mapped[str] = mapped_column(String, nullable=False)
    technique: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[OutcomeType] = mapped_column(SAEnum(OutcomeType), nullable=False)
    evasion_used: Mapped[str | None] = mapped_column(String, nullable=True)
    signal_strength: Mapped[float] = mapped_column(Float, default=1.0)
    notes: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 8: Run tests — verify they pass**

```bash
cd backend && pytest tests/test_models.py -v
# Expected: 3 PASSED
```

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/
git commit -m "feat: all ORM models (Engagement, Agent, Task, Bid, Finding, KnowledgeGraphEntry)"
```

---

### Task 5: Alembic Migrations

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_initial.py`

- [ ] **Step 1: Initialize Alembic**

```bash
cd backend && alembic init alembic
```

- [ ] **Step 2: Update alembic/env.py for async**

```python
# backend/alembic/env.py
import asyncio
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool
from alembic import context
from app.config import settings
from app.database import Base

# import all models so Base knows about them
from app.models import engagement, agent, task, finding, knowledge  # noqa

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Generate initial migration**

```bash
cd backend && alembic revision --autogenerate -m "initial"
# Expected: Generates backend/alembic/versions/xxxx_initial.py
```

- [ ] **Step 4: Run migration**

```bash
cd backend && alembic upgrade head
# Expected: Running upgrade -> xxxx, OK
```

- [ ] **Step 5: Verify tables exist**

```bash
docker exec -it $(docker compose ps -q postgres) psql -U forge -d forge -c "\dt"
# Expected: lists engagements, agents, tasks, bids, findings, knowledge_entries
```

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/ backend/alembic.ini
git commit -m "feat: alembic async migrations, initial schema"
```

---

### Task 6: FastAPI Skeleton + Health Endpoint

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Write health test**

```python
# backend/tests/test_health.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health_returns_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd backend && pytest tests/test_health.py -v
# Expected: ImportError or 404
```

- [ ] **Step 3: Write conftest.py**

```python
# backend/tests/conftest.py
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "postgresql+asyncpg://forge:forge@localhost:5432/forge_test"

@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
```

- [ ] **Step 4: Write main.py**

```python
# backend/app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: nothing yet — services connect lazily
    yield
    # shutdown: nothing yet


app = FastAPI(
    title="FORGE",
    description="Framework for Offensive Reasoning, Generation and Exploitation",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
```

- [ ] **Step 5: Run test — verify it passes**

```bash
cd backend && pytest tests/test_health.py -v
# Expected: PASSED
```

- [ ] **Step 6: Start dev server and verify manually**

```bash
make dev
# In another terminal:
curl http://localhost:8000/api/v1/health
# Expected: {"status":"ok","version":"0.1.0"}
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py backend/tests/
git commit -m "feat: FastAPI skeleton with health endpoint and test fixtures"
```

---

## Plan 1 Complete

At this point you have:
- All Docker services running (PostgreSQL, Redis, Qdrant, Neo4j)
- All ORM models defined and migrated
- FastAPI app running with a passing health test
- Full test infrastructure in place

**Next:** Plan 2 — Core Engine (Knowledge Store + Task Board + Strategic Brain)
