import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# Use sha256_crypt to match what auth.py now uses (bcrypt 5.x compat issue)
try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
except Exception:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

from app.database import Base, get_db
from app.main import app
from app.models.user import User, UserRole
from app.api.deps import get_current_user

pytestmark = pytest.mark.asyncio
TEST_DB = "postgresql+asyncpg://forge:forge@localhost:5432/forge_test"


@pytest.fixture(autouse=True)
async def seeded_db():
    """Create all tables in forge_test, seed one user, then drop everything after the test."""
    engine = create_async_engine(TEST_DB)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as s:
        u = User(email="u@test.com", hashed_password=pwd_context.hash("x"), role=UserRole.analyst)
        s.add(u)
        await s.commit()
        await s.refresh(u)
        seeded_db.user = u
        seeded_db.engine = engine
        seeded_db.session_factory = session_factory
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def authed_client():
    """AsyncClient with both get_current_user and get_db overridden to use forge_test.

    Overriding get_db is essential: without it the app's get_db would open a
    connection to the production database (forge) and FK constraints would fail
    because the test user only exists in forge_test.
    """
    session_factory = seeded_db.session_factory

    async def _override_user():
        return seeded_db.user

    async def _override_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_create_api_key(authed_client):
    r = await authed_client.post("/api/v1/api-keys/", json={"name": "my-key"})
    assert r.status_code == 201
    data = r.json()
    assert "key" in data
    assert data["prefix"] == data["key"][:8]
    assert data["name"] == "my-key"


async def test_list_api_keys(authed_client):
    await authed_client.post("/api/v1/api-keys/", json={"name": "k1"})
    await authed_client.post("/api/v1/api-keys/", json={"name": "k2"})
    r = await authed_client.get("/api/v1/api-keys/")
    assert r.status_code == 200
    assert len(r.json()) == 2


async def test_revoke_api_key(authed_client):
    created = (await authed_client.post("/api/v1/api-keys/", json={"name": "tok"})).json()
    key_id = created["id"]
    r = await authed_client.delete(f"/api/v1/api-keys/{key_id}")
    assert r.status_code == 204
    listed = (await authed_client.get("/api/v1/api-keys/")).json()
    assert not any(k["id"] == key_id for k in listed)


async def test_revoke_other_user_key_404(authed_client):
    created = (await authed_client.post("/api/v1/api-keys/", json={"name": "tok"})).json()
    key_id = created["id"]

    # Seed a second user using the same test engine so it is visible to the
    # overridden get_db session.
    async with seeded_db.session_factory() as s:
        u2 = User(email="other@test.com", hashed_password=pwd_context.hash("x"), role=UserRole.viewer)
        s.add(u2)
        await s.commit()
        await s.refresh(u2)

    app.dependency_overrides[get_current_user] = lambda: u2
    r = await authed_client.delete(f"/api/v1/api-keys/{key_id}")
    assert r.status_code == 404
    app.dependency_overrides[get_current_user] = lambda: seeded_db.user
