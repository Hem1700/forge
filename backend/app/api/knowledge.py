from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.knowledge import KnowledgeGraphEntry

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


class KnowledgeEntryResponse(BaseModel):
    # from_attributes lets pydantic read ORM attributes; aliases map the
    # underlying model's `technique` and `signal_strength` fields onto the
    # public API shape (`technique_id`, `score`).
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    technique_id: str = Field(validation_alias="technique")
    attack_class: str
    outcome: str
    score: float = Field(validation_alias="signal_strength")
    tech_stack: list[str]
    created_at: datetime


@router.get("/", response_model=list[KnowledgeEntryResponse])
async def list_knowledge_entries(
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeEntryResponse]:
    result = await db.execute(select(KnowledgeGraphEntry))
    entries = result.scalars().all()
    return [KnowledgeEntryResponse.model_validate(e) for e in entries]


@router.get("/attack-class/{attack_class}", response_model=list[KnowledgeEntryResponse])
async def list_by_attack_class(
    attack_class: str,
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeEntryResponse]:
    result = await db.execute(
        select(KnowledgeGraphEntry).where(KnowledgeGraphEntry.attack_class == attack_class)
    )
    entries = result.scalars().all()
    return [KnowledgeEntryResponse.model_validate(e) for e in entries]
