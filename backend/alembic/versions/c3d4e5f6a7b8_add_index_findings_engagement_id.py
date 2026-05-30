"""add index on findings.engagement_id

Revision ID: c3d4e5f6a7b8
Revises: df01a85bf9ab
Create Date: 2026-05-28
"""
from __future__ import annotations
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "df01a85bf9ab"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_findings_engagement_id", "findings", ["engagement_id"])


def downgrade() -> None:
    op.drop_index("ix_findings_engagement_id", table_name="findings")
