"""Tests for Redis sliding-window rate limiting."""
from __future__ import annotations
import uuid
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import AsyncClient, ASGITransport
from passlib.context import CryptContext
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

import app.brain.llm_factory as _llm_factory_mod
from app.brain.llm_factory import (
    Provider, RateLimitQueuedError, _check_rate_limit, _DEFAULT_RATE_LIMITS,
)
from app.database import Base, get_db
from app.main import app
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.org_rate_limit import OrgRateLimitConfig
from app.api.deps import get_current_user

TEST_DB = "postgresql+asyncpg://forge:forge@localhost:5432/forge_test"
_pwd = CryptContext(schemes=["sha256_crypt"], deprecated="auto")


@pytest.fixture(autouse=True)
def _set_test_fernet(monkeypatch):
    from cryptography.fernet import Fernet as F
    monkeypatch.setattr(_llm_factory_mod, "_fernet", F(F.generate_key()))


@pytest_asyncio.fixture
async def org_http_client():
    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as db:
        org = Organization(name=f"rl-test-{uuid.uuid4()}")
        db.add(org)
        await db.commit()
        await db.refresh(org)
        user = User(
            email=f"rl-{uuid.uuid4()}@test.forge",
            hashed_password=_pwd.hash("x"),
            role=UserRole.super_admin,
            org_id=org.id,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    async def _db():
        async with sf() as s:
            yield s
    async def _user():
        return user

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


def _mock_redis(rpm_ok=True, tpm_ok=True):
    """Return a mock Redis whose eval() allows or denies based on params."""
    mock = AsyncMock()
    mock.eval = AsyncMock(side_effect=[
        1 if rpm_ok else 0,
        1 if tpm_ok else 0,
    ] * 4)  # enough for retries
    mock.zremrangebyscore = AsyncMock(return_value=0)
    mock.zcard = AsyncMock(return_value=0)
    mock.zadd = AsyncMock(return_value=1)
    mock.expire = AsyncMock(return_value=True)
    return mock


@pytest.mark.asyncio
async def test_no_org_id_skips_rate_limit():
    await _check_rate_limit(org_id=None, provider=Provider.anthropic, estimated_tokens=1000)


@pytest.mark.asyncio
async def test_unknown_provider_skips_rate_limit():
    # Provider.azure is in _DEFAULT_RATE_LIMITS; ollama is not
    # Test that a provider not in defaults is skipped gracefully
    # (we'll patch _DEFAULT_RATE_LIMITS to simulate missing provider)
    with patch.dict(_llm_factory_mod._DEFAULT_RATE_LIMITS, {}, clear=True):
        await _check_rate_limit(org_id=uuid.uuid4(), provider=Provider.anthropic, estimated_tokens=500)


@pytest.mark.asyncio
async def test_allowed_when_under_limit():
    mock_redis = _mock_redis(rpm_ok=True, tpm_ok=True)
    with patch.object(_llm_factory_mod, "_get_rl_redis", AsyncMock(return_value=mock_redis)):
        await _check_rate_limit(
            org_id=uuid.uuid4(), provider=Provider.anthropic, estimated_tokens=100
        )
    assert mock_redis.eval.call_count >= 2


@pytest.mark.asyncio
async def test_rpm_exceeded_raises_after_retries():
    mock_redis = _mock_redis(rpm_ok=False, tpm_ok=True)
    # All retries fail
    mock_redis.eval = AsyncMock(return_value=0)
    with patch.object(_llm_factory_mod, "_get_rl_redis", AsyncMock(return_value=mock_redis)):
        with patch("asyncio.sleep", AsyncMock()):  # don't actually sleep
            with pytest.raises(RateLimitQueuedError) as exc_info:
                await _check_rate_limit(
                    org_id=uuid.uuid4(), provider=Provider.anthropic, estimated_tokens=100
                )
    assert exc_info.value.provider == "anthropic"
    assert exc_info.value.retry_after_seconds > 0


@pytest.mark.asyncio
async def test_default_limits_defined_for_major_providers():
    for prov in ["anthropic", "openai", "bedrock", "azure"]:
        assert prov in _DEFAULT_RATE_LIMITS
        assert _DEFAULT_RATE_LIMITS[prov]["tpm"] > 0
        assert _DEFAULT_RATE_LIMITS[prov]["rpm"] > 0


@pytest.mark.asyncio
async def test_rate_limit_error_fields():
    org_id = uuid.uuid4()
    err = RateLimitQueuedError(org_id=org_id, provider="anthropic", retry_after_seconds=8)
    assert err.provider == "anthropic"
    assert err.retry_after_seconds == 8
    assert "anthropic" in str(err)


@pytest.mark.asyncio
async def test_rest_get_rate_limits(org_http_client):
    mock_redis = _mock_redis()
    with patch.object(_llm_factory_mod, "_get_rl_redis", AsyncMock(return_value=mock_redis)):
        resp = await org_http_client.get("/api/v1/org/rate-limits")
    assert resp.status_code == 200
    data = resp.json()
    assert "anthropic" in data
    assert "tpm_limit" in data["anthropic"]
    assert "rpm_limit" in data["anthropic"]


@pytest.mark.asyncio
async def test_rest_set_rate_limit(org_http_client):
    resp = await org_http_client.put("/api/v1/org/rate-limits", json={
        "provider": "anthropic",
        "tpm_limit": 50000,
        "rpm_limit": 25,
    })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_rest_set_unknown_provider_returns_400(org_http_client):
    resp = await org_http_client.put("/api/v1/org/rate-limits", json={
        "provider": "fakeprovider",
        "tpm_limit": 1000,
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_rest_delete_rate_limits(org_http_client):
    await org_http_client.put("/api/v1/org/rate-limits", json={"provider": "openai", "tpm_limit": 1000})
    resp = await org_http_client.delete("/api/v1/org/rate-limits")
    assert resp.status_code == 200
    assert resp.json()["reset_to_defaults"] is True
