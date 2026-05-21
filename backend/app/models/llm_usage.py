# backend/app/models/llm_usage.py
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Numeric, String, Integer
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LLMUsageEvent(Base):
    __tablename__ = "llm_usage_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    task: Mapped[str] = mapped_column(String(50), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    compression_applied: Mapped[bool] = mapped_column(nullable=False, default=False)
    original_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compression_savings_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
