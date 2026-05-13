import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models.user import User, UserRole
from app.api.deps import get_current_user

pytestmark = pytest.mark.asyncio

VIEWER = User(email="v@forge.io", hashed_password="x", role=UserRole.viewer)
ANALYST = User(email="a@forge.io", hashed_password="x", role=UserRole.analyst)
ADMIN = User(email="adm@forge.io", hashed_password="x", role=UserRole.admin)


async def test_unauthenticated_request_returns_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/v1/engagements/")
    assert r.status_code == 401


async def test_viewer_cannot_create_engagement():
    app.dependency_overrides[get_current_user] = lambda: VIEWER
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/engagements/", json={"target_url": "http://x.com", "target_type": "web"})
    app.dependency_overrides.clear()
    assert r.status_code == 403


async def test_viewer_cannot_delete_engagement():
    app.dependency_overrides[get_current_user] = lambda: VIEWER
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.delete("/api/v1/engagements/00000000-0000-0000-0000-000000000001")
    app.dependency_overrides.clear()
    assert r.status_code == 403


async def test_analyst_cannot_delete_engagement():
    app.dependency_overrides[get_current_user] = lambda: ANALYST
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.delete("/api/v1/engagements/00000000-0000-0000-0000-000000000001")
    app.dependency_overrides.clear()
    assert r.status_code == 403


async def test_admin_delete_passes_auth_check():
    app.dependency_overrides[get_current_user] = lambda: ADMIN
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.delete("/api/v1/engagements/00000000-0000-0000-0000-000000000001")
    app.dependency_overrides.clear()
    # Auth passes (admin has permission) — will get 404 from DB (no real DB) but NOT 401/403
    assert r.status_code not in (401, 403)
