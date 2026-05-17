from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.engagement import Engagement
from app.models.user import User
from app.models.finding import Finding
from app.models.knowledge import KnowledgeGraphEntry

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/stats")
async def system_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    engagements_count = (
        await db.execute(
            select(func.count()).select_from(Engagement).where(
                Engagement.org_id == current_user.org_id
            )
        )
    ).scalar_one()
    findings_count = (
        await db.execute(
            select(func.count())
            .select_from(Finding)
            .join(Engagement, Finding.engagement_id == Engagement.id)
            .where(Engagement.org_id == current_user.org_id)
        )
    ).scalar_one()
    knowledge_count = (
        await db.execute(
            select(func.count())
            .select_from(KnowledgeGraphEntry)
            .join(Engagement, KnowledgeGraphEntry.engagement_id == Engagement.id)
            .where(Engagement.org_id == current_user.org_id)
        )
    ).scalar_one()
    return {
        "engagements": int(engagements_count),
        "findings": int(findings_count),
        "knowledge_entries": int(knowledge_count),
    }
