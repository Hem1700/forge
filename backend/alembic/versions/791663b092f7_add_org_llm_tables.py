"""add_org_llm_tables

Revision ID: 791663b092f7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-18 22:10:08.522158

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '791663b092f7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_usage_events',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('org_id', sa.Uuid(), nullable=False),
        sa.Column('engagement_id', sa.Uuid(), nullable=True),
        sa.Column('task', sa.String(length=50), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('cost_usd', sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_llm_usage_events_engagement_id'), 'llm_usage_events', ['engagement_id'], unique=False)
    op.create_index(op.f('ix_llm_usage_events_org_id'), 'llm_usage_events', ['org_id'], unique=False)

    op.create_table(
        'org_llm_audit_log',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('org_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_org_llm_audit_log_org_id'), 'org_llm_audit_log', ['org_id'], unique=False)

    op.create_table(
        'org_llm_credentials',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('org_id', sa.Uuid(), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('encrypted_key', sa.LargeBinary(), nullable=True),
        sa.Column('region', sa.String(length=50), nullable=True),
        sa.Column('endpoint', sa.String(length=500), nullable=True),
        sa.Column('extra', sa.JSON(), nullable=True),
        sa.Column('last_tested_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('org_id', 'provider'),
    )
    op.create_index(op.f('ix_org_llm_credentials_org_id'), 'org_llm_credentials', ['org_id'], unique=False)

    op.create_table(
        'org_llm_task_config',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('org_id', sa.Uuid(), nullable=False),
        sa.Column('task_type', sa.String(length=50), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('max_tokens', sa.Integer(), nullable=True),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('org_id', 'task_type'),
    )
    op.create_index(op.f('ix_org_llm_task_config_org_id'), 'org_llm_task_config', ['org_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_org_llm_task_config_org_id'), table_name='org_llm_task_config')
    op.drop_table('org_llm_task_config')
    op.drop_index(op.f('ix_org_llm_credentials_org_id'), table_name='org_llm_credentials')
    op.drop_table('org_llm_credentials')
    op.drop_index(op.f('ix_org_llm_audit_log_org_id'), table_name='org_llm_audit_log')
    op.drop_table('org_llm_audit_log')
    op.drop_index(op.f('ix_llm_usage_events_org_id'), table_name='llm_usage_events')
    op.drop_index(op.f('ix_llm_usage_events_engagement_id'), table_name='llm_usage_events')
    op.drop_table('llm_usage_events')
