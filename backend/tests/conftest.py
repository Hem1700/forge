import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database import Base, get_db
from app.main import app
from app.models.user import User, UserRole
from app.api.deps import get_current_user

# Import all models so tables are registered with Base.metadata before create_all
from app.models import engagement, agent, task, finding, knowledge, user, api_key, organization  # noqa: F401

TEST_DATABASE_URL = "postgresql+asyncpg://forge:forge@localhost:5432/forge_test"
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")


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


@pytest_asyncio.fixture
async def test_super_admin(db_session):
    # Super admin has all permissions — ensures every existing test passes
    # regardless of which route they call (including DELETE which needs admin+).
    user_obj = User(
        email="superadmin@test.forge",
        hashed_password=pwd_context.hash("testpass"),
        role=UserRole.super_admin,
    )
    db_session.add(user_obj)
    await db_session.commit()
    await db_session.refresh(user_obj)
    return user_obj


@pytest_asyncio.fixture
async def http_client(db_session, test_super_admin):
    """AsyncClient with get_db and get_current_user overridden.

    All existing tests run as a super_admin so every route permission check
    passes — preserves prior test behaviour while routes now require auth.
    """
    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return test_super_admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
