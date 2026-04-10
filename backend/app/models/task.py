import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, DateTime, JSON, Enum as SAEnum, ForeignKey, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Priority(str, PyEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class TaskStatus(str, PyEnum):
    open = "open"
    bidding = "bidding"
    assigned = "assigned"
    awaiting_human_gate = "awaiting_human_gate"
    complete = "complete"
    rejected = "rejected"


class NoiseLevel(str, PyEnum):
    low = "low"
    medium = "medium"
    high = "high"


class BidOutcome(str, PyEnum):
    won = "won"
    lost = "lost"
    expired = "expired"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engagements.id"), nullable=False)
    hypothesis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    surface: Mapped[str] = mapped_column(String, nullable=False)
    required_confidence: Mapped[float] = mapped_column(Float, default=0.6)
    priority: Mapped[Priority] = mapped_column(SAEnum(Priority), default=Priority.medium)
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), default=TaskStatus.open)
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    event_log: Mapped[list] = mapped_column(JSON, default=list)


class Bid(Base):
    __tablename__ = "bids"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    basis: Mapped[str] = mapped_column(String, default="")
    estimated_probes: Mapped[int] = mapped_column(Integer, default=1)
    noise_level: Mapped[NoiseLevel] = mapped_column(SAEnum(NoiseLevel), default=NoiseLevel.medium)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    outcome: Mapped[BidOutcome | None] = mapped_column(SAEnum(BidOutcome), nullable=True)
