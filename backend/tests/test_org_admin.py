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
        admin = User(email="admin@forge.io", hashed_password=pwd_context.hash("x"), role=UserRole.admin)
        viewer = User(email="viewer@forge.io", hashed_password=pwd_context.hash("x"), role=UserRole.viewer)
        s.add(admin)
        s.add(viewer)
        await s.commit()
        await s.refresh(admin)
        await s.refresh(viewer)
        seeded_db.admin = admin
        seeded_db.viewer = viewer
        seeded_db.session_factory = session_factory
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def admin_client():
    async def _db():
        async with seeded_db.session_factory() as s:
            yield s
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: seeded_db.admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def viewer_client():
    async def _db():
        async with seeded_db.session_factory() as s:
            yield s
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: seeded_db.viewer
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_list_users_as_admin(admin_client):
    r = await admin_client.get("/api/v1/org/users")
    assert r.status_code == 200
    emails = [u["email"] for u in r.json()]
    assert "admin@forge.io" in emails
    assert "viewer@forge.io" in emails


async def test_list_users_forbidden_for_viewer(viewer_client):
    r = await viewer_client.get("/api/v1/org/users")
    assert r.status_code == 403


async def test_update_role(admin_client):
    r = await admin_client.patch(
        f"/api/v1/org/users/{seeded_db.viewer.id}/role",
        json={"role": "analyst"},
    )
    assert r.status_code == 200
    assert r.json()["role"] == "analyst"


async def test_admin_cannot_promote_to_super_admin(admin_client):
    r = await admin_client.patch(
        f"/api/v1/org/users/{seeded_db.viewer.id}/role",
        json={"role": "super_admin"},
    )
    assert r.status_code == 403


async def test_delete_user(admin_client):
    r = await admin_client.delete(f"/api/v1/org/users/{seeded_db.viewer.id}")
    assert r.status_code == 204


async def test_cannot_delete_self(admin_client):
    r = await admin_client.delete(f"/api/v1/org/users/{seeded_db.admin.id}")
    assert r.status_code == 400
