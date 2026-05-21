"""Tests for per-org monthly budget enforcement."""
from __future__ import annotations
import uuid
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import AsyncClient, ASGITransport
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from unittest.mock import AsyncMock, MagicMock, patch

import app.brain.llm_factory as _llm_factory_mod
from app.brain.llm_factory import (
    BudgetExceededError, TrackedLLM, TaskType, Provider, _check_budget, _update_budget_spend,
)
from app.database import Base, get_db
from app.main import app
from app.models.org_llm import OrgBudget
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.api.deps import get_current_user

TEST_DB = "postgresql+asyncpg://forge:forge@localhost:5432/forge_test"
_pwd = CryptContext(schemes=["sha256_crypt"], deprecated="auto")


@pytest.fixture(autouse=True)
def _set_test_fernet(monkeypatch):
    """Provide a real Fernet instance so _encrypt_key/_decrypt_key work in tests."""
    key = Fernet.generate_key()
    monkeypatch.setattr(_llm_factory_mod, "_fernet", Fernet(key))


@pytest_asyncio.fixture
async def org_http_client():
    """AsyncClient where the test user belongs to a real org (needed for audit log NOT NULL)."""
    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        org = Organization(name=f"test-org-{uuid.uuid4()}")
        db.add(org)
        await db.commit()
        await db.refresh(org)

        user = User(
            email=f"admin-{uuid.uuid4()}@test.forge",
            hashed_password=_pwd.hash("testpass"),
            role=UserRole.super_admin,
            org_id=org.id,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    async def override_db():
        async with session_factory() as session:
            yield session

    async def override_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
def org_with_budget(db_session):
    """Returns a coroutine that creates an org with a budget."""
    async def _create(limit_usd: float, hard_cap: bool = True, current_spend: float = 0.0):
        org = Organization(name=f"budget-test-{uuid.uuid4()}")
        db_session.add(org)
        await db_session.commit()
        await db_session.refresh(org)
        budget = OrgBudget(
            org_id=org.id,
            monthly_limit_usd=limit_usd,
            current_spend_usd=current_spend,
            hard_cap=hard_cap,
            alert_threshold_pct=80,
            reset_day=1,
        )
        db_session.add(budget)
        await db_session.commit()
        return org, budget
    return _create


@pytest.mark.asyncio
async def test_no_budget_allows_call():
    """No OrgBudget row = unlimited; _check_budget should not raise."""
    org_id = uuid.uuid4()
    # No DB row for this org_id — should pass silently
    await _check_budget(
        org_id=org_id,
        provider=Provider.anthropic,
        model="claude-sonnet-4-6",
        max_tokens=4000,
        prompt_len=1000,
    )


@pytest.mark.asyncio
async def test_no_org_id_allows_call():
    await _check_budget(
        org_id=None,
        provider=Provider.anthropic,
        model="claude-sonnet-4-6",
        max_tokens=4000,
        prompt_len=1000,
    )



@pytest.mark.asyncio
async def test_soft_cap_allows_call_when_over_limit(org_with_budget):
    """hard_cap=False → call proceeds even if over budget."""
    org, budget = await org_with_budget(limit_usd=0.01, hard_cap=False, current_spend=0.01)
    # Should NOT raise
    await _check_budget(
        org_id=org.id,
        provider=Provider.anthropic,
        model="claude-sonnet-4-6",
        max_tokens=4000,
        prompt_len=1000,
    )



@pytest.mark.asyncio
async def test_budget_exceeded_error_fields():
    org_id = uuid.uuid4()
    err = BudgetExceededError(org_id=org_id, limit=5.0, current=4.9, estimated=0.2)
    assert err.limit == 5.0
    assert err.current == 4.9
    assert "exceeded" in str(err).lower()


@pytest.mark.asyncio
async def test_budget_rest_get_no_budget(org_http_client):
    """GET /budget with no budget configured returns unlimited status."""
    resp = await org_http_client.get("/api/v1/org/llm/budget")
    assert resp.status_code == 200
    data = resp.json()
    assert data["unlimited"] is True
    assert data["configured"] is False


@pytest.mark.asyncio
async def test_budget_rest_set_and_get(org_http_client):
    resp = await org_http_client.put("/api/v1/org/llm/budget", json={
        "monthly_limit_usd": 50.0,
        "reset_day": 1,
        "alert_threshold_pct": 80,
        "hard_cap": True,
    })
    assert resp.status_code == 200
    resp2 = await org_http_client.get("/api/v1/org/llm/budget")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["configured"] is True
    assert data["monthly_limit_usd"] == 50.0
    assert data["hard_cap"] is True


@pytest.mark.asyncio
async def test_budget_rest_invalid_reset_day(org_http_client):
    resp = await org_http_client.put("/api/v1/org/llm/budget", json={
        "monthly_limit_usd": 50.0,
        "reset_day": 31,
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_budget_rest_delete(org_http_client):
    await org_http_client.put("/api/v1/org/llm/budget", json={"monthly_limit_usd": 10.0})
    resp = await org_http_client.delete("/api/v1/org/llm/budget")
    assert resp.status_code == 200
    resp2 = await org_http_client.get("/api/v1/org/llm/budget")
    assert resp2.json()["unlimited"] is True
