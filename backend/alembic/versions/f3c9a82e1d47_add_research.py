"""Add research column to findings.

Revision ID: f3c9a82e1d47
Revises: e1b5a47fc839
Create Date: 2026-04-29
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'f3c9a82e1d47'
down_revision: Union[str, None] = 'e1b5a47fc839'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('findings', sa.Column('research', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('findings', 'research')
