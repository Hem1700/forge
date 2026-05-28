import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.user import User, UserRole
from app.api.deps import get_current_user

# Import all models so their tables are registered with Base.metadata
# before create_all runs. Without this, FK-bearing tables fail to resolve.
from app.models import engagement, agent, task, finding, knowledge, user, api_key  # noqa: F401

pytestmark = pytest.mark.asyncio
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
TEST_DB = "postgresql+asyncpg://forge:forge@localhost:5432/forge_test"


@pytest.fixture(autouse=True)
async def seeded_db():
    engine = create_async_engine(TEST_DB)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as s:
        # Genuine platform admin: super_admin role + is_platform_admin=True
        platform_admin = User(
            email="platform@forge.io",
            hashed_password=pwd_context.hash("x"),
            role=UserRole.super_admin,
            is_platform_admin=True,
        )
        # Org owner: super_admin role but NOT a platform admin
        org_owner = User(
            email="owner@org-a.io",
            hashed_password=pwd_context.hash("x"),
            role=UserRole.super_admin,
            is_platform_admin=False,
        )
        # Regular inactive user for cross-org enumeration test
        regular = User(
            email="r@forge.io",
            hashed_password=pwd_context.hash("x"),
            role=UserRole.viewer,
            is_active=False,
        )
        s.add(platform_admin)
        s.add(org_owner)
        s.add(regular)
        await s.commit()
        await s.refresh(platform_admin)
        await s.refresh(org_owner)
        await s.refresh(regular)
        seeded_db.platform_admin = platform_admin
        seeded_db.sadmin = platform_admin  # backwards-compat alias
        seeded_db.org_owner = org_owner
        seeded_db.regular = regular
        seeded_db.session_factory = session_factory
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def sa_client():
    """Client authenticated as a genuine platform admin."""
    async def _db():
        async with seeded_db.session_factory() as s:
            yield s
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: seeded_db.platform_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def org_owner_client():
    """Client authenticated as an org owner (super_admin role, is_platform_admin=False)."""
    async def _db():
        async with seeded_db.session_factory() as s:
            yield s
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: seeded_db.org_owner
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def admin_client():
    admin_user = User(email="a@b.com", hashed_password="x", role=UserRole.admin)
    async def _db():
        async with seeded_db.session_factory() as s:
            yield s
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Existing positive tests — platform admin CAN do everything
# ---------------------------------------------------------------------------

async def test_list_all_users_as_platform_admin(sa_client):
    r = await sa_client.get("/api/v1/admin/users")
    assert r.status_code == 200
    emails = [u["email"] for u in r.json()]
    assert "r@forge.io" in emails  # includes inactive users


async def test_list_all_users_forbidden_for_admin(admin_client):
    r = await admin_client.get("/api/v1/admin/users")
    assert r.status_code == 403


async def test_set_any_role_as_platform_admin(sa_client):
    r = await sa_client.patch(
        f"/api/v1/admin/users/{seeded_db.regular.id}/role",
        json={"role": "analyst"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "analyst"


async def test_provision_user(sa_client):
    r = await sa_client.post(
        "/api/v1/admin/provision",
        json={"email": "new@forge.io", "password": "secure123", "role": "analyst"},
    )
    assert r.status_code == 201
    assert r.json()["role"] == "analyst"


# ---------------------------------------------------------------------------
# Cross-org isolation tests — org owner (super_admin, no is_platform_admin)
# MUST be blocked from all /admin/* endpoints
# ---------------------------------------------------------------------------

async def test_list_users_forbidden_for_org_owner(org_owner_client):
    """An org founder with super_admin role but no is_platform_admin gets 403."""
    r = await org_owner_client.get("/api/v1/admin/users")
    assert r.status_code == 403


async def test_set_role_forbidden_for_org_owner(org_owner_client):
    """Org owner cannot change roles across orgs."""
    dummy_id = uuid.uuid4()
    r = await org_owner_client.patch(
        f"/api/v1/admin/users/{dummy_id}/role",
        json={"role": "analyst"},
    )
    assert r.status_code == 403


async def test_provision_forbidden_for_org_owner(org_owner_client):
    """Org owner cannot provision users via the platform endpoint."""
    r = await org_owner_client.post(
        "/api/v1/admin/provision",
        json={"email": "injected@evil.io", "password": "x", "role": "super_admin"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Optional org_id filter — platform admin CAN filter by org
# ---------------------------------------------------------------------------

async def test_list_users_with_org_filter(sa_client):
    """?org_id= filter returns an empty list rather than erroring."""
    random_org = uuid.uuid4()
    r = await sa_client.get(f"/api/v1/admin/users?org_id={random_org}")
    assert r.status_code == 200
    assert r.json() == []
