"""Add triage columns to findings.

Revision ID: c4f1e8d9b3a2
Revises: b712a4c9f103
Create Date: 2026-04-24
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c4f1e8d9b3a2'
down_revision: Union[str, None] = 'b712a4c9f103'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TRIAGE_VALUES = ('unreviewed', 'accepted', 'false_positive', 'fixed')


def upgrade() -> None:
    triage_enum = sa.Enum(*TRIAGE_VALUES, name='triagestatus')
    triage_enum.create(op.get_bind(), checkfirst=True)
    op.add_column('findings', sa.Column('triage_status', triage_enum, nullable=False, server_default='unreviewed'))
    op.add_column('findings', sa.Column('triage_notes', sa.String(), nullable=False, server_default=''))
    op.add_column('findings', sa.Column('triage_updated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('findings', 'triage_updated_at')
    op.drop_column('findings', 'triage_notes')
    op.drop_column('findings', 'triage_status')
    sa.Enum(name='triagestatus').drop(op.get_bind(), checkfirst=True)
