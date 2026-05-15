"""WebSocket auth and org-isolation tests.

The WS endpoint reads its DB session from `AsyncSessionLocal` directly
(WS handshakes can't easily use FastAPI's `Depends`), so we monkey-patch
that factory at module level to share the test session factory.
"""
import asyncio
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app import database as db_module
from app import main as main_module
from app.config import settings
from app.database import Base
from app.main import app
from app.models import organization, user, engagement as engagement_model, engagement_event  # noqa: F401
from app.models.engagement import Engagement
from app.models.engagement_event import EngagementEvent
from app.models.organization import Organization
from app.models.user import User, UserRole

TEST_DATABASE_URL = "postgresql+asyncpg://forge:forge@localhost:5432/forge_test"


def _make_token(user_id: uuid.UUID) -> str:
    return jwt.encode(
        {"sub": str(user_id), "exp": datetime.utcnow() + timedelta(hours=1)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


@pytest.fixture
def ws_fixtures(monkeypatch):
    """Create two orgs, two users, one engagement per org. Patch AsyncSessionLocal.

    Uses NullPool so every session opens a fresh connection in whatever
    asyncio loop is currently running — TestClient runs the WS handler in
    its own loop, distinct from this fixture's loop, and asyncpg
    connections are loop-bound. NullPool means no cross-loop sharing.
    """
    async def setup():
        engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            org_a = Organization(name="OrgA")
            org_b = Organization(name="OrgB")
            session.add_all([org_a, org_b])
            await session.flush()

            user_a = User(
                email="a@a.test",
                hashed_password="x",
                role=UserRole.analyst,
                org_id=org_a.id,
            )
            user_b = User(
                email="b@b.test",
                hashed_password="x",
                role=UserRole.analyst,
                org_id=org_b.id,
            )
            session.add_all([user_a, user_b])
            await session.flush()

            eng_a = Engagement(target_url="https://a.test", target_type="web", org_id=org_a.id)
            session.add(eng_a)
            await session.flush()

            session.add_all([
                EngagementEvent(
                    engagement_id=eng_a.id,
                    type="progress",
                    payload={"detail": "first"},
                    timestamp=datetime.utcnow(),
                ),
                EngagementEvent(
                    engagement_id=eng_a.id,
                    type="progress",
                    payload={"detail": "second"},
                    timestamp=datetime.utcnow(),
                ),
            ])
            await session.commit()
            return engine, {
                "user_a": user_a.id,
                "user_b": user_b.id,
                "eng_a": eng_a.id,
            }

    engine, ids = asyncio.run(setup())
    # Build a fresh session factory keyed to the WS handler's loop.
    # NullPool ensures connections are created on demand in the caller's loop.
    handler_factory = async_sessionmaker(
        create_async_engine(TEST_DATABASE_URL, poolclass=NullPool),
        expire_on_commit=False,
    )
    monkeypatch.setattr(db_module, "AsyncSessionLocal", handler_factory)
    monkeypatch.setattr(main_module, "AsyncSessionLocal", handler_factory)
    from app.ws import stream as stream_module
    monkeypatch.setattr(stream_module, "AsyncSessionLocal", handler_factory)

    yield ids

    async def teardown():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(teardown())


def _connect_expecting_close(client: TestClient, url: str) -> int:
    """Connect and return the close code. Raises if the server actually accepts."""
    from starlette.websockets import WebSocketDisconnect
    try:
        with client.websocket_connect(url) as ws:
            ws.receive_text()  # should never get here
    except WebSocketDisconnect as exc:
        return exc.code
    raise AssertionError("expected the server to close the socket")


def test_ws_rejects_missing_token(ws_fixtures):
    client = TestClient(app)
    code = _connect_expecting_close(client, f"/ws/{ws_fixtures['eng_a']}")
    assert code == 4401


def test_ws_rejects_invalid_token(ws_fixtures):
    client = TestClient(app)
    code = _connect_expecting_close(client, f"/ws/{ws_fixtures['eng_a']}?token=garbage")
    assert code == 4401


def test_ws_rejects_cross_org_subscriber(ws_fixtures):
    """User B (org B) must not be able to subscribe to org A's engagement."""
    client = TestClient(app)
    token_b = _make_token(ws_fixtures["user_b"])
    code = _connect_expecting_close(
        client, f"/ws/{ws_fixtures['eng_a']}?token={token_b}"
    )
    assert code == 4403


def test_ws_accepts_owner_and_replays(ws_fixtures):
    """User A connecting with ?since=0 receives both seeded events."""
    client = TestClient(app)
    token_a = _make_token(ws_fixtures["user_a"])
    with client.websocket_connect(
        f"/ws/{ws_fixtures['eng_a']}?token={token_a}&since=0"
    ) as ws:
        first = ws.receive_json()
        second = ws.receive_json()
    assert first["payload"]["detail"] == "first"
    assert second["payload"]["detail"] == "second"
    assert first["id"] < second["id"]
