"""Add engagement_events table for event replay.

Revision ID: b712a4c9f103
Revises: 8a9c2f7d4b1e
Create Date: 2026-04-20
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = 'b712a4c9f103'
down_revision: Union[str, None] = '8a9c2f7d4b1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'engagement_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('engagement_id', UUID(as_uuid=True), sa.ForeignKey('engagements.id'), nullable=False),
        sa.Column('type', sa.String(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_engagement_events_engagement_id', 'engagement_events', ['engagement_id'])
    op.create_index('ix_engagement_events_timestamp', 'engagement_events', ['timestamp'])


def downgrade() -> None:
    op.drop_index('ix_engagement_events_timestamp', table_name='engagement_events')
    op.drop_index('ix_engagement_events_engagement_id', table_name='engagement_events')
    op.drop_table('engagement_events')
