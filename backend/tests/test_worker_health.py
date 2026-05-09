"""Tests for GET /api/v1/health/worker — surfaces Arq worker liveness."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_worker_health_up_returns_arq_stats(http_client):
    """Heartbeat key present → status=up + stats string forwarded as-is."""
    fake_pool = MagicMock()
    fake_pool.get = AsyncMock(
        return_value=b"j_complete=5 j_failed=0 j_retried=0 j_ongoing=2 queued=1"
    )
    with patch("app.main.get_pool", new=AsyncMock(return_value=fake_pool)):
        response = await http_client.get("/api/v1/health/worker")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "up"
    assert "j_complete=5" in body["stats"]
    assert "j_ongoing=2" in body["stats"]


@pytest.mark.asyncio
async def test_worker_health_down_when_key_missing(http_client):
    """No heartbeat key in Redis → status=down."""
    fake_pool = MagicMock()
    fake_pool.get = AsyncMock(return_value=None)
    with patch("app.main.get_pool", new=AsyncMock(return_value=fake_pool)):
        response = await http_client.get("/api/v1/health/worker")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "down"
    assert body["stats"] is None


@pytest.mark.asyncio
async def test_worker_health_unknown_when_redis_unreachable(http_client):
    """Redis errors should not 500 the endpoint — degrade to status=unknown."""
    with patch("app.main.get_pool", new=AsyncMock(side_effect=ConnectionError("redis down"))):
        response = await http_client.get("/api/v1/health/worker")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unknown"
    assert body["stats"] is None


@pytest.mark.asyncio
async def test_worker_health_decodes_string_value(http_client):
    """Some redis-py configs return str instead of bytes — handle both."""
    fake_pool = MagicMock()
    fake_pool.get = AsyncMock(return_value="j_complete=0 j_ongoing=0 queued=0")
    with patch("app.main.get_pool", new=AsyncMock(return_value=fake_pool)):
        response = await http_client.get("/api/v1/health/worker")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "up"
    assert body["stats"] == "j_complete=0 j_ongoing=0 queued=0"
