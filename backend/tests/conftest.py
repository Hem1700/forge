import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.database import Base, get_db
from app.main import app

# Import all models so their tables are registered with Base.metadata
# before create_all runs. Without this, FK-bearing tables (findings,
# tasks, agents) fail to resolve.
from app.models import engagement, agent, task, finding, knowledge  # noqa: F401

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


@pytest_asyncio.fixture
async def http_client(db_session):
    """AsyncClient wired to the FastAPI app with get_db overridden to the test session.

    The override yields the same db_session fixture, so API handlers and the
    test share one transactional view of the DB.
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
