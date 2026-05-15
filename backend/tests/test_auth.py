import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base, get_db
from app.main import app

# Import all models so metadata is fully populated before create_all.
from app.models import engagement, agent, task, finding, knowledge, user, api_key, organization  # noqa: F401

pytestmark = pytest.mark.asyncio
TEST_DB = "postgresql+asyncpg://forge:forge@localhost:5432/forge_test"

REG = {"org_name": "TestOrg"}


@pytest.fixture
async def client():
    """AsyncClient wired to the FastAPI app with get_db overridden to an
    isolated test-database session.  Tables are created fresh for each test
    and dropped on teardown so tests never share state.
    """
    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def test_first_register_becomes_super_admin(client):
    r = await client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "pass1234", **REG})
    assert r.status_code == 201
    token = r.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["role"] == "super_admin"


async def test_duplicate_org_name_rejected(client):
    # Org name already taken — second registrant must use an invite link
    await client.post("/api/v1/auth/register", json={"email": "first@b.com", "password": "pass1234", **REG})
    r = await client.post("/api/v1/auth/register", json={"email": "second@b.com", "password": "pass1234", **REG})
    assert r.status_code == 400
    assert "invite" in r.json()["detail"].lower()


async def test_first_in_new_org_becomes_super_admin(client):
    # Register first user in OrgA, second user in OrgB — OrgB user is also super_admin
    await client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "pass1234", "org_name": "OrgA"})
    r = await client.post("/api/v1/auth/register", json={"email": "c@d.com", "password": "pass1234", "org_name": "OrgB"})
    assert r.status_code == 201
    token = r.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["role"] == "super_admin"


async def test_duplicate_email_rejected(client):
    await client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "pass", **REG})
    r = await client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "other", **REG})
    assert r.status_code == 400


async def test_login_valid(client):
    await client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "secret", **REG})
    r = await client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "secret"})
    assert r.status_code == 200
    assert "access_token" in r.json()


async def test_login_wrong_password(client):
    await client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "secret", **REG})
    r = await client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "wrong"})
    assert r.status_code == 401


async def test_me_without_token(client):
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_me_with_valid_token(client):
    reg = await client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "pass", **REG})
    token = reg.json()["access_token"]
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "a@b.com"
    assert "hashed_password" not in data
    assert data["org_name"] == "TestOrg"
