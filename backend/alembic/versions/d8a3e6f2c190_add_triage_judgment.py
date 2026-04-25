"""Add triage_judgment column to findings.

Revision ID: d8a3e6f2c190
Revises: c4f1e8d9b3a2
Create Date: 2026-04-24
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'd8a3e6f2c190'
down_revision: Union[str, None] = 'c4f1e8d9b3a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('findings', sa.Column('triage_judgment', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('findings', 'triage_judgment')
