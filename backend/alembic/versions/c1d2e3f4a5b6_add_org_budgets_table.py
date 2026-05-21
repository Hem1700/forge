"""add org_budgets table

Revision ID: c1d2e3f4a5b6
Revises: a9f1c3e7b204
Create Date: 2026-05-20

Adds org_budgets table for per-org monthly LLM budget enforcement.
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op
import uuid

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "a9f1c3e7b204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_budgets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("monthly_limit_usd", sa.Float(), nullable=False),
        sa.Column("current_spend_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("alert_threshold_pct", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("hard_cap", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("reset_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id"),
    )
    op.create_index("ix_org_budgets_org_id", "org_budgets", ["org_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_org_budgets_org_id", table_name="org_budgets")
    op.drop_table("org_budgets")
