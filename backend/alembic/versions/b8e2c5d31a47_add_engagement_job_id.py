"""Add job_id column to engagements for worker-crash recovery.

Revision ID: b8e2c5d31a47
Revises: a07c5d2b91f8
Create Date: 2026-05-09
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b8e2c5d31a47'
down_revision: Union[str, None] = 'a07c5d2b91f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('engagements', sa.Column('job_id', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('engagements', 'job_id')
