"""add org_rate_limit_configs table

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-05-21
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "org_rate_limit_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("tpm_limit", sa.Integer(), nullable=True),
        sa.Column("rpm_limit", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "provider"),
    )
    op.create_index("ix_org_rate_limit_configs_org_id", "org_rate_limit_configs", ["org_id"])

def downgrade() -> None:
    op.drop_index("ix_org_rate_limit_configs_org_id", table_name="org_rate_limit_configs")
    op.drop_table("org_rate_limit_configs")
