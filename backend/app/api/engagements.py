from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.engagement import Engagement, EngagementStatus
from app.models.finding import Finding

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
            "recommendation": "",
            "confidence_score": f.confidence_score,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in findings
    ]


@router.delete("/{engagement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_engagement(
    engagement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Response:
    engagement = await db.get(Engagement, engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="Engagement not found")
    await db.delete(engagement)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
