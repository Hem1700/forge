import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, DateTime, JSON, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_url: Mapped[str] = mapped_column(String, nullable=False)
    target_type: Mapped[str] = mapped_column(String, default="web")
    target_path: Mapped[str | None] = mapped_column(String, nullable=True)
    target_scope: Mapped[list] = mapped_column(JSON, default=list)
    target_out_of_scope: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[EngagementStatus] = mapped_column(SAEnum(EngagementStatus), default=EngagementStatus.pending)
    gate_status: Mapped[GateStatus] = mapped_column(SAEnum(GateStatus), default=GateStatus.gate_1)
    semantic_model: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
