from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, DateTime, JSON, Enum as SAEnum, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.finding import Finding
    from app.models.task import Task
    from app.models.agent import Agent
    from app.models.knowledge import KnowledgeGraphEntry
    from app.models.engagement_event import EngagementEvent


class EngagementStatus(str, PyEnum):
    pending = "pending"
    running = "running"
    paused_at_gate = "paused_at_gate"
    complete = "complete"
    aborted = "aborted"


class GateStatus(str, PyEnum):
    gate_1 = "gate_1"
    gate_2 = "gate_2"
    gate_3 = "gate_3"
    complete = "complete"


class Engagement(Base):
    __tablename__ = "engagements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    target_url: Mapped[str] = mapped_column(String, nullable=False)
    target_type: Mapped[str] = mapped_column(String, default="web")
    target_path: Mapped[str | None] = mapped_column(String, nullable=True)
    target_scope: Mapped[list] = mapped_column(JSON, default=list)
    target_out_of_scope: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[EngagementStatus] = mapped_column(SAEnum(EngagementStatus), default=EngagementStatus.pending)
    gate_status: Mapped[GateStatus] = mapped_column(SAEnum(GateStatus), default=GateStatus.gate_1)
    semantic_model: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Arq job id of the most recent pipeline dispatch. Lets the API check on
    # startup whether the worker that owned this engagement is still alive —
    # if Arq no longer has the job, the worker died mid-pipeline and we
    # mark the engagement aborted instead of letting it hang in `running`.
    job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("organizations.id"), nullable=True, index=True
    )

    # Cascade: deleting an engagement removes all child rows automatically.
    findings: Mapped[list[Finding]] = relationship(
        "Finding", back_populates=None, cascade="all, delete-orphan", passive_deletes=True
    )
    tasks: Mapped[list[Task]] = relationship(
        "Task", back_populates=None, cascade="all, delete-orphan", passive_deletes=True
    )
    agents: Mapped[list[Agent]] = relationship(
        "Agent", back_populates=None, cascade="all, delete-orphan", passive_deletes=True
    )
    knowledge_entries: Mapped[list[KnowledgeGraphEntry]] = relationship(
        "KnowledgeGraphEntry", back_populates=None, cascade="all, delete-orphan", passive_deletes=True
    )
    events: Mapped[list[EngagementEvent]] = relationship(
        "EngagementEvent", back_populates=None, cascade="all, delete-orphan", passive_deletes=True
    )
