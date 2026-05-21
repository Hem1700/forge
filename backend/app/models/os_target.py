# backend/app/models/os_target.py
import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import DateTime, Integer, JSON, LargeBinary, String, Boolean
from sqlalchemy import Uuid, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OSTarget(Base):
    __tablename__ = "os_targets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    auth_type: Mapped[str] = mapped_column(String(20), nullable=False)  # key | password | agent
    encrypted_credential: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    access_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="agentless")
    collector_sudo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fingerprint: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
