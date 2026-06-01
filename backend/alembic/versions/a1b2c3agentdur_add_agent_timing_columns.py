"""add agent timing columns

Revision ID: a1b2c3agentdur
Revises: g7h8i9j0k1l2
Create Date: 2026-05-31
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3agentdur"
down_revision: str | None = "g7h8i9j0k1l2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agents", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agents", sa.Column("duration_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "duration_ms")
    op.drop_column("agents", "completed_at")
    op.drop_column("agents", "started_at")
