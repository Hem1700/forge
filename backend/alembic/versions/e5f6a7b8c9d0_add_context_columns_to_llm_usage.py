"""add context compression columns to llm_usage_events

Revision ID: e5f6a7b8c9d0
Revises: c1d2e3f4a5b6
Create Date: 2026-05-21
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("llm_usage_events", sa.Column("compression_applied", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("llm_usage_events", sa.Column("original_tokens", sa.Integer(), nullable=True))
    op.add_column("llm_usage_events", sa.Column("compression_savings_pct", sa.Numeric(5, 2), nullable=True))

def downgrade() -> None:
    op.drop_column("llm_usage_events", "compression_savings_pct")
    op.drop_column("llm_usage_events", "original_tokens")
    op.drop_column("llm_usage_events", "compression_applied")
