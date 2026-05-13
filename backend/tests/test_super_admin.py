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
        sadmin = User(email="sa@forge.io", hashed_password=pwd_context.hash("x"), role=UserRole.super_admin)
        regular = User(email="r@forge.io", hashed_password=pwd_context.hash("x"), role=UserRole.viewer, is_active=False)
        s.add(sadmin)
        s.add(regular)
        await s.commit()
        await s.refresh(sadmin)
        await s.refresh(regular)
        seeded_db.sadmin = sadmin
        seeded_db.regular = regular
        seeded_db.session_factory = session_factory
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def sa_client():
    async def _db():
        async with seeded_db.session_factory() as s:
            yield s
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: seeded_db.sadmin
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


async def test_list_all_users_as_super_admin(sa_client):
    r = await sa_client.get("/api/v1/admin/users")
    assert r.status_code == 200
    emails = [u["email"] for u in r.json()]
    assert "r@forge.io" in emails  # includes inactive users


async def test_list_all_users_forbidden_for_admin(admin_client):
    r = await admin_client.get("/api/v1/admin/users")
    assert r.status_code == 403


async def test_set_any_role_as_super_admin(sa_client):
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
