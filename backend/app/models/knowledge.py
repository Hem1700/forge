import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, DateTime, JSON, Enum as SAEnum, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class OutcomeType(str, PyEnum):
    confirmed = "confirmed"
    false_positive = "false_positive"
    inconclusive = "inconclusive"


class KnowledgeGraphEntry(Base):
    __tablename__ = "knowledge_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engagements.id"), nullable=False)
    tech_stack: Mapped[list] = mapped_column(JSON, default=list)
    app_type: Mapped[str] = mapped_column(String, default="")
    attack_class: Mapped[str] = mapped_column(String, nullable=False)
    technique: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[OutcomeType] = mapped_column(SAEnum(OutcomeType), nullable=False)
    evasion_used: Mapped[str | None] = mapped_column(String, nullable=True)
    signal_strength: Mapped[float] = mapped_column(Float, default=1.0)
    notes: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
