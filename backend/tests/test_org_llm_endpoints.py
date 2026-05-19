# backend/tests/test_org_llm_endpoints.py
"""Tests for /api/v1/org/llm/* endpoints."""
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
from app.database import Base, get_db
from app.main import app
from app.models.user import User, UserRole
from app.models.organization import Organization
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


# ── Providers ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_providers_returns_four(org_http_client):
    resp = await org_http_client.get("/api/v1/org/llm/providers")
    assert resp.status_code == 200
    data = resp.json()
    names = {p["provider"] for p in data}
    assert names == {"anthropic", "openai", "bedrock", "azure"}
    for item in data:
        assert "required_fields" in item
        assert "description" in item


# ── Credentials ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_credentials_initially_unconfigured(org_http_client):
    resp = await org_http_client.get("/api/v1/org/llm/credentials")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 4
    for item in data:
        assert item["configured"] is False


@pytest.mark.asyncio
async def test_upsert_credential_never_returns_key(org_http_client):
    resp = await org_http_client.put(
        "/api/v1/org/llm/credentials/anthropic",
        json={"api_key": "sk-ant-supersecret"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Key must never appear in the response
    assert "api_key" not in body
    assert "encrypted_key" not in body
    assert body["provider"] == "anthropic"
    assert body["configured"] is True


@pytest.mark.asyncio
async def test_upsert_credential_shows_in_list(org_http_client):
    await org_http_client.put(
        "/api/v1/org/llm/credentials/openai",
        json={"api_key": "sk-openai-abc123"},
    )
    resp = await org_http_client.get("/api/v1/org/llm/credentials")
    assert resp.status_code == 200
    by_provider = {item["provider"]: item for item in resp.json()}
    assert by_provider["openai"]["configured"] is True
    assert "api_key" not in by_provider["openai"]


@pytest.mark.asyncio
async def test_upsert_unknown_provider_returns_400(org_http_client):
    resp = await org_http_client.put(
        "/api/v1/org/llm/credentials/fakeprovider",
        json={"api_key": "key"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_revoke_credential(org_http_client):
    await org_http_client.put(
        "/api/v1/org/llm/credentials/anthropic",
        json={"api_key": "sk-ant-todelete"},
    )
    del_resp = await org_http_client.delete("/api/v1/org/llm/credentials/anthropic")
    assert del_resp.status_code == 200
    assert del_resp.json()["revoked"] is True

    list_resp = await org_http_client.get("/api/v1/org/llm/credentials")
    by_provider = {item["provider"]: item for item in list_resp.json()}
    assert by_provider["anthropic"]["configured"] is False


@pytest.mark.asyncio
async def test_revoke_nonexistent_credential_returns_404(org_http_client):
    resp = await org_http_client.delete("/api/v1/org/llm/credentials/openai")
    assert resp.status_code == 404


# ── Credential test probe ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_credential_test_endpoint_ok(org_http_client):
    await org_http_client.put(
        "/api/v1/org/llm/credentials/anthropic",
        json={"api_key": "sk-ant-fake"},
    )

    mock_llm_instance = AsyncMock()
    mock_llm_instance.ainvoke = AsyncMock(return_value=MagicMock(content="hi"))

    with patch("app.brain.llm_factory._build_anthropic", return_value=mock_llm_instance), \
         patch("app.brain.llm_factory._resolve_credentials", new=AsyncMock(return_value=MagicMock())):
        resp = await org_http_client.post("/api/v1/org/llm/credentials/anthropic/test")

    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_credential_test_endpoint_failure(org_http_client):
    await org_http_client.put(
        "/api/v1/org/llm/credentials/anthropic",
        json={"api_key": "sk-ant-bad"},
    )

    with patch("app.brain.llm_factory._build_anthropic", side_effect=Exception("auth failed")), \
         patch("app.brain.llm_factory._resolve_credentials", new=AsyncMock(return_value=MagicMock())):
        resp = await org_http_client.post("/api/v1/org/llm/credentials/anthropic/test")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "auth failed" in body["error"]


# ── Task config ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_task_config_defaults(org_http_client):
    resp = await org_http_client.get("/api/v1/org/llm/task-config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["preset"] == "balanced"
    assert isinstance(body["tasks"], dict)
    assert len(body["tasks"]) > 0
    for task_val in body["tasks"].values():
        assert task_val["from_default"] is True


@pytest.mark.asyncio
async def test_set_task_config_smart_preset(org_http_client):
    resp = await org_http_client.put(
        "/api/v1/org/llm/task-config",
        json={"preset": "smart"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["preset"] == "smart"
    assert body["tasks_configured"] > 0


@pytest.mark.asyncio
async def test_set_task_config_cheap_preset(org_http_client):
    resp = await org_http_client.put(
        "/api/v1/org/llm/task-config",
        json={"preset": "cheap"},
    )
    assert resp.status_code == 200
    assert resp.json()["preset"] == "cheap"


@pytest.mark.asyncio
async def test_set_task_config_balanced_clears_rows(org_http_client):
    await org_http_client.put("/api/v1/org/llm/task-config", json={"preset": "smart"})
    await org_http_client.put("/api/v1/org/llm/task-config", json={"preset": "balanced"})
    resp = await org_http_client.get("/api/v1/org/llm/task-config")
    body = resp.json()
    assert body["preset"] == "balanced"
    for v in body["tasks"].values():
        assert v["from_default"] is True


@pytest.mark.asyncio
async def test_set_task_config_custom(org_http_client):
    resp = await org_http_client.put(
        "/api/v1/org/llm/task-config",
        json={
            "custom": {
                "agent_brain": {"provider": "openai", "model": "gpt-4o"},
                "findings_judge": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
            }
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["preset"] == "custom"
    assert body["tasks_configured"] == 2


@pytest.mark.asyncio
async def test_set_task_config_invalid_task_returns_400(org_http_client):
    resp = await org_http_client.put(
        "/api/v1/org/llm/task-config",
        json={"custom": {"nonexistent_task_xyz": {"provider": "openai", "model": "gpt-4o"}}},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_set_task_config_invalid_provider_returns_400(org_http_client):
    resp = await org_http_client.put(
        "/api/v1/org/llm/task-config",
        json={"custom": {"agent_brain": {"provider": "fakeprovider", "model": "gpt-4o"}}},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_set_task_config_both_fields_returns_400(org_http_client):
    resp = await org_http_client.put(
        "/api/v1/org/llm/task-config",
        json={
            "preset": "smart",
            "custom": {"agent_brain": {"provider": "openai", "model": "gpt-4o"}},
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_set_task_config_neither_field_returns_400(org_http_client):
    resp = await org_http_client.put("/api/v1/org/llm/task-config", json={})
    assert resp.status_code == 400


# ── Usage ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_usage_empty(org_http_client):
    resp = await org_http_client.get("/api/v1/org/llm/usage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_cost_usd"] == 0.0
    assert body["rows"] == []


@pytest.mark.asyncio
async def test_get_usage_invalid_since_returns_400(org_http_client):
    resp = await org_http_client.get("/api/v1/org/llm/usage?since=not-a-date")
    assert resp.status_code == 400


# ── Audit log ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_log_written_on_upsert(org_http_client):
    await org_http_client.put(
        "/api/v1/org/llm/credentials/anthropic",
        json={"api_key": "sk-ant-audittest"},
    )
    resp = await org_http_client.get("/api/v1/org/llm/audit")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) >= 1
    actions = [e["action"] for e in entries]
    assert "set_key" in actions


@pytest.mark.asyncio
async def test_audit_log_written_on_revoke(org_http_client):
    await org_http_client.put(
        "/api/v1/org/llm/credentials/anthropic",
        json={"api_key": "sk-ant-revoketest"},
    )
    await org_http_client.delete("/api/v1/org/llm/credentials/anthropic")
    resp = await org_http_client.get("/api/v1/org/llm/audit")
    entries = resp.json()
    actions = [e["action"] for e in entries]
    assert "revoke" in actions


@pytest.mark.asyncio
async def test_audit_log_entries_have_required_fields(org_http_client):
    await org_http_client.put(
        "/api/v1/org/llm/credentials/openai",
        json={"api_key": "sk-openai-fields"},
    )
    resp = await org_http_client.get("/api/v1/org/llm/audit")
    for entry in resp.json():
        assert "id" in entry
        assert "action" in entry
        assert "created_at" in entry
        assert "payload" in entry
