import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, DateTime, JSON, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class AgentType(str, PyEnum):
    recon = "recon"
    logic_modeler = "logic_modeler"
    probe = "probe"
    evasion = "evasion"
    deep_exploit = "deep_exploit"
    child = "child"
    validator = "validator"


class AgentStatus(str, PyEnum):
    idle = "idle"
    bidding = "bidding"
    running = "running"
    terminated = "terminated"
    completed = "completed"


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("engagements.id"), nullable=False)
    type: Mapped[AgentType] = mapped_column(SAEnum(AgentType), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    spawned_reason: Mapped[str] = mapped_column(String, default="")
    status: Mapped[AgentStatus] = mapped_column(SAEnum(AgentStatus), default=AgentStatus.idle)
    current_task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    signal_history: Mapped[list] = mapped_column(JSON, default=list)
    termination_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    tools: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
