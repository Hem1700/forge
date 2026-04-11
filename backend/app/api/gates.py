from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.engagements import EngagementResponse
from app.database import get_db
from app.models.engagement import Engagement, EngagementStatus, GateStatus

router = APIRouter(prefix="/api/v1/gates", tags=["gates"])


class GateDecisionRequest(BaseModel):
    approved: bool
    notes: str = ""


_GATE_ORDER: list[GateStatus] = [
    GateStatus.gate_1,
    GateStatus.gate_2,
    GateStatus.gate_3,
    GateStatus.complete,
]


def _advance_gate(current: GateStatus) -> GateStatus:
    """Return the next gate in the progression, stopping at complete."""
    try:
        idx = _GATE_ORDER.index(current)
    except ValueError:
        return current
    if idx >= len(_GATE_ORDER) - 1:
        return GateStatus.complete
    return _GATE_ORDER[idx + 1]


@router.post("/{engagement_id}/decide", response_model=EngagementResponse)
async def decide_gate(
    engagement_id: uuid.UUID,
    payload: GateDecisionRequest,
    db: AsyncSession = Depends(get_db),
) -> EngagementResponse:
    engagement = await db.get(Engagement, engagement_id)
    if engagement is None:
        raise HTTPException(status_code=404, detail="Engagement not found")

    if payload.approved:
        new_gate = _advance_gate(engagement.gate_status)
        engagement.gate_status = new_gate
        if new_gate == GateStatus.complete:
            engagement.status = EngagementStatus.complete
            engagement.completed_at = datetime.utcnow()
    else:
        engagement.status = EngagementStatus.aborted

    await db.commit()
    await db.refresh(engagement)
    return EngagementResponse.model_validate(engagement)
