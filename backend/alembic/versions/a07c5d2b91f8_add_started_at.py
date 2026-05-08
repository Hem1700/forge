"""Add started_at column to engagements.

Revision ID: a07c5d2b91f8
Revises: f3c9a82e1d47
Create Date: 2026-05-08
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a07c5d2b91f8'
down_revision: Union[str, None] = 'f3c9a82e1d47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('engagements', sa.Column('started_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('engagements', 'started_at')
