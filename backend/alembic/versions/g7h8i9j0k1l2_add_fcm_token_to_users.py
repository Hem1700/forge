"""add fcm_token to users

Revision ID: g7h8i9j0k1l2
Revises: 07e54f3065d1
Create Date: 2026-05-30
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision: str = "g7h8i9j0k1l2"
down_revision: str | None = "07e54f3065d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("fcm_token", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "fcm_token")
