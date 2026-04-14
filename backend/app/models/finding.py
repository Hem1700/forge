import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, DateTime, JSON, Enum as SAEnum, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Severity(str, PyEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class ValidationStatus(str, PyEnum):
    pending = "pending"
    validated = "validated"
    rejected = "rejected"


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engagements.id"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    vulnerability_class: Mapped[str] = mapped_column(String, nullable=False)
    affected_surface: Mapped[str] = mapped_column(String, nullable=False)
    reproduction_steps: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    cvss_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[Severity] = mapped_column(SAEnum(Severity), default=Severity.medium)
    validation_status: Mapped[ValidationStatus] = mapped_column(SAEnum(ValidationStatus), default=ValidationStatus.pending)
    validation_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    exploit_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    poc_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
