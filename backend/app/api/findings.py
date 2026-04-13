from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.finding import Finding
from app.models.engagement import Engagement
from app.brain.exploit_engine import ExploitEngine

router = APIRouter(prefix="/api/v1/findings", tags=["findings"])


def _serialize_finding(f: Finding) -> dict:
    return {
        "id": str(f.id),
        "engagement_id": str(f.engagement_id),
        "title": f.title,
        "severity": f.severity.value,
        "vulnerability_class": f.vulnerability_class,
        "affected_surface": f.affected_surface,
        "description": f.description,
        "evidence": f.evidence,
        "confidence_score": f.confidence_score,
        "validation_status": f.validation_status.value,
        "reproduction_steps": f.reproduction_steps,
        "exploit_detail": f.exploit_detail,
        "created_at": f.created_at.isoformat(),
    }


@router.get("/{finding_id}")
async def get_finding(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return _serialize_finding(finding)


@router.post("/{finding_id}/exploit")
async def generate_exploit(
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    finding = await db.get(Finding, finding_id)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if finding.exploit_detail:
        return finding.exploit_detail

    engagement = await db.get(Engagement, finding.engagement_id)
    context = {
        "target_url": engagement.target_url if engagement else None,
        "target_path": engagement.target_path if engagement else None,
        "target_type": engagement.target_type if engagement else "web",
        "app_type": (engagement.semantic_model or {}).get("app_type", "unknown") if engagement else "unknown",
    }

    engine = ExploitEngine()
    exploit = await engine.generate(_serialize_finding(finding), context)

    finding.exploit_detail = exploit
    await db.commit()
    return exploit
