"""add index on findings.engagement_id

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-05-28
"""
from __future__ import annotations
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_findings_engagement_id", "findings", ["engagement_id"])


def downgrade() -> None:
    op.drop_index("ix_findings_engagement_id", table_name="findings")
