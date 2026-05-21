"""add os_targets table

Revision ID: f6a7b8c9d0e1
Revises: c1d2e3f4a5b6
Create Date: 2026-05-21
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "os_targets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("engagement_id", sa.Uuid(), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("auth_type", sa.String(20), nullable=False),
        sa.Column("encrypted_credential", sa.LargeBinary(), nullable=True),
        sa.Column("access_mode", sa.String(20), nullable=False, server_default="agentless"),
        sa.Column("collector_sudo", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("fingerprint", sa.JSON(), nullable=True),
        sa.Column("collected_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["engagement_id"], ["engagements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_os_targets_engagement_id", "os_targets", ["engagement_id"])

def downgrade() -> None:
    op.drop_index("ix_os_targets_engagement_id", table_name="os_targets")
    op.drop_table("os_targets")
