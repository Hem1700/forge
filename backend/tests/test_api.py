import uuid

import pytest


PAYLOAD = {
    "target_url": "https://example.com",
    "target_scope": ["example.com"],
    "target_out_of_scope": ["admin.example.com"],
}


@pytest.mark.asyncio
async def test_create_engagement(http_client):
    response = await http_client.post("/api/v1/engagements/", json=PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["target_url"] == PAYLOAD["target_url"]
    assert body["status"] == "pending"
    assert body["gate_status"] == "gate_1"


@pytest.mark.asyncio
async def test_list_engagements(http_client):
    create_resp = await http_client.post("/api/v1/engagements/", json=PAYLOAD)
    assert create_resp.status_code == 201

    response = await http_client.get("/api/v1/engagements/")
    assert response.status_code == 200
    items = response.json()
    assert isinstance(items, list)
    assert len(items) >= 1


@pytest.mark.asyncio
async def test_get_engagement(http_client):
    create_resp = await http_client.post("/api/v1/engagements/", json=PAYLOAD)
    engagement_id = create_resp.json()["id"]

    response = await http_client.get(f"/api/v1/engagements/{engagement_id}")
    assert response.status_code == 200
    assert response.json()["id"] == engagement_id


@pytest.mark.asyncio
async def test_get_engagement_not_found(http_client):
    missing_id = uuid.uuid4()
    response = await http_client.get(f"/api/v1/engagements/{missing_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_status(http_client):
    create_resp = await http_client.post("/api/v1/engagements/", json=PAYLOAD)
    engagement_id = create_resp.json()["id"]

    response = await http_client.patch(
        f"/api/v1/engagements/{engagement_id}/status",
        json={"status": "running"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "running"


@pytest.mark.asyncio
async def test_delete_engagement(http_client):
    create_resp = await http_client.post("/api/v1/engagements/", json=PAYLOAD)
    engagement_id = create_resp.json()["id"]

    response = await http_client.delete(f"/api/v1/engagements/{engagement_id}")
    assert response.status_code == 204

    follow_up = await http_client.get(f"/api/v1/engagements/{engagement_id}")
    assert follow_up.status_code == 404
