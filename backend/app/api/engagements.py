from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from playwright.async_api import async_playwright
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.agent import Agent
from app.models.engagement import Engagement, EngagementStatus
from app.models.finding import Finding
from app.models.knowledge import KnowledgeGraphEntry
from app.models.task import Bid, Task

router = APIRouter(prefix="/api/v1/engagements", tags=["engagements"])


class CreateEngagementRequest(BaseModel):
    target_url: str
    target_type: str = "web"
    target_path: str | None = None
    target_scope: list[str] = []
    target_out_of_scope: list[str] = []


class UpdateStatusRequest(BaseModel):
    status: str


class EngagementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    target_url: str
    target_type: str
    target_path: str | None = None
    status: str
    gate_status: str
    created_at: datetime
    completed_at: datetime | None = None


@router.post("/", response_model=EngagementResponse, status_code=status.HTTP_201_CREATED)
async def create_engagement(
    payload: CreateEngagementRequest,
    db: AsyncSession = Depends(get_db),
) -> EngagementResponse:
    engagement = Engagement(
        target_url=payload.target_url,
        target_type=payload.target_type,
        target_path=payload.target_path,
        target_scope=payload.target_scope,
        target_out_of_scope=payload.target_out_of_scope,
    )
    db.add(engagement)
    await db.commit()
    await db.refresh(engagement)
    return EngagementResponse.model_validate(engagement)


@router.get("/", response_model=list[EngagementResponse])
async def list_engagements(
    db: AsyncSession = Depends(get_db),
) -> list[EngagementResponse]:
    result = await db.execute(select(Engagement))
    engagements = result.scalars().all()
    return [EngagementResponse.model_validate(e) for e in engagements]


@router.get("/{engagement_id}", response_model=EngagementResponse)
async def get_engagement(
    engagement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> EngagementResponse:
    engagement = await db.get(Engagement, engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return EngagementResponse.model_validate(engagement)


@router.patch("/{engagement_id}/status", response_model=EngagementResponse)
async def update_engagement_status(
    engagement_id: uuid.UUID,
    payload: UpdateStatusRequest,
    db: AsyncSession = Depends(get_db),
) -> EngagementResponse:
    engagement = await db.get(Engagement, engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="Engagement not found")
    try:
        engagement.status = EngagementStatus(payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid status: {payload.status}") from exc
    await db.commit()
    await db.refresh(engagement)
    return EngagementResponse.model_validate(engagement)


@router.get("/{engagement_id}/findings")
async def get_engagement_findings(
    engagement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    engagement = await db.get(Engagement, engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="Engagement not found")
    result = await db.execute(select(Finding).where(Finding.engagement_id == engagement_id))
    findings = result.scalars().all()
    return [
        {
            "id": str(f.id),
            "severity": f.severity.value,
            "title": f.title,
            "vulnerability_class": f.vulnerability_class,
            "affected_surface": f.affected_surface,
            "description": f.description,
            "evidence": f.evidence,
            "reproduction_steps": f.reproduction_steps,
            "recommendation": "",
            "confidence_score": f.confidence_score,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "poc_detail": f.poc_detail,
            "exploit_script": f.exploit_script,
            "exploit_execution": f.exploit_execution,
        }
        for f in findings
    ]


@router.post("/{engagement_id}/report/pdf")
async def generate_pdf_report(
    engagement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    engagement = await db.get(Engagement, engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="Engagement not found")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(
                f"{settings.frontend_url.rstrip('/')}/print/{engagement_id}",
                wait_until="networkidle",
            )
            pdf_bytes = await page.pdf(format="A4", print_background=True)
        finally:
            await browser.close()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=forge_report_{engagement_id}.pdf"
        },
    )


@router.delete("/{engagement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_engagement(
    engagement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    engagement = await db.get(Engagement, engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="Engagement not found")
    # cascade delete children (no ON DELETE CASCADE in schema)
    task_ids = (await db.execute(select(Task.id).where(Task.engagement_id == engagement_id))).scalars().all()
    if task_ids:
        await db.execute(delete(Bid).where(Bid.task_id.in_(task_ids)))
    await db.execute(delete(Finding).where(Finding.engagement_id == engagement_id))
    await db.execute(delete(Task).where(Task.engagement_id == engagement_id))
    await db.execute(delete(Agent).where(Agent.engagement_id == engagement_id))
    await db.execute(delete(KnowledgeGraphEntry).where(KnowledgeGraphEntry.engagement_id == engagement_id))
    await db.delete(engagement)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
