# backend/tests/test_pdf_report.py
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_engagement(eid):
    """Minimal engagement ORM-like object."""
    eng = MagicMock()
    eng.id = eid
    eng.target_url = "https://example.com"
    return eng


@pytest.mark.asyncio
async def test_pdf_report_returns_pdf_content_type(http_client, db_session):
    """POST /{id}/report/pdf returns application/pdf when engagement exists."""
    from app.models.engagement import Engagement, EngagementStatus

    eid = uuid.uuid4()
    eng = Engagement(
        id=eid,
        target_url="https://example.com",
        target_type="web",
        status=EngagementStatus.complete,
    )
    db_session.add(eng)
    await db_session.commit()

    fake_pdf = b"%PDF-1.4 fake pdf bytes"

    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_load_state = AsyncMock()
    mock_page.pdf = AsyncMock(return_value=fake_pdf)

    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()

    mock_chromium = MagicMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_pw = AsyncMock()
    mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw.__aexit__ = AsyncMock(return_value=None)
    mock_pw.chromium = mock_chromium

    with patch("app.api.engagements.async_playwright", return_value=mock_pw):
        resp = await http_client.post(f"/api/v1/engagements/{eid}/report/pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


@pytest.mark.asyncio
async def test_pdf_report_content_disposition_filename(http_client, db_session):
    """Content-Disposition header contains the correct engagement ID filename."""
    from app.models.engagement import Engagement, EngagementStatus

    eid = uuid.uuid4()
    eng = Engagement(
        id=eid,
        target_url="https://example.com",
        target_type="web",
        status=EngagementStatus.complete,
    )
    db_session.add(eng)
    await db_session.commit()

    fake_pdf = b"%PDF-1.4 fake"

    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_load_state = AsyncMock()
    mock_page.pdf = AsyncMock(return_value=fake_pdf)

    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()

    mock_chromium = MagicMock()
    mock_chromium.launch = AsyncMock(return_value=mock_browser)

    mock_pw = AsyncMock()
    mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw.__aexit__ = AsyncMock(return_value=None)
    mock_pw.chromium = mock_chromium

    with patch("app.api.engagements.async_playwright", return_value=mock_pw):
        resp = await http_client.post(f"/api/v1/engagements/{eid}/report/pdf")

    assert resp.status_code == 200
    disposition = resp.headers.get("content-disposition", "")
    assert f"forge_report_{eid}.pdf" in disposition


@pytest.mark.asyncio
async def test_pdf_report_404_on_unknown_engagement(http_client, db_session):
    """POST /{id}/report/pdf returns 404 when engagement does not exist."""
    eid = uuid.uuid4()

    resp = await http_client.post(f"/api/v1/engagements/{eid}/report/pdf")

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
