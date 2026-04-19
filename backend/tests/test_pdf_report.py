# backend/tests/test_pdf_report.py
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_playwright_factory():
    """Returns a factory that builds a mock playwright context for a given PDF bytes value."""
    def _make(fake_pdf: bytes):
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
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

        return mock_pw, mock_browser
    return _make


@pytest.mark.asyncio
async def test_pdf_report_returns_pdf_content_type(http_client, db_session, mock_playwright_factory):
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

    mock_pw, mock_browser = mock_playwright_factory(b"%PDF-1.4 fake pdf bytes")

    with patch("app.api.engagements.async_playwright", return_value=mock_pw):
        resp = await http_client.post(f"/api/v1/engagements/{eid}/report/pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    mock_browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_pdf_report_content_disposition_filename(http_client, db_session, mock_playwright_factory):
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

    mock_pw, mock_browser = mock_playwright_factory(b"%PDF-1.4 fake")

    with patch("app.api.engagements.async_playwright", return_value=mock_pw):
        resp = await http_client.post(f"/api/v1/engagements/{eid}/report/pdf")

    assert resp.status_code == 200
    disposition = resp.headers.get("content-disposition", "")
    assert f"forge_report_{eid}.pdf" in disposition
    mock_browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_pdf_report_404_on_unknown_engagement(http_client, db_session):
    """POST /{id}/report/pdf returns 404 when engagement does not exist."""
    eid = uuid.uuid4()

    resp = await http_client.post(f"/api/v1/engagements/{eid}/report/pdf")

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
