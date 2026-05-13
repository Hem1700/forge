"""Add users and api_keys tables.

Revision ID: aac91bff9e86
Revises: b8e2c5d31a47
Create Date: 2026-05-12
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'aac91bff9e86'
down_revision: Union[str, None] = 'b8e2c5d31a47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the UserRole enum type
    enum_type = postgresql.ENUM('viewer', 'analyst', 'admin', 'super_admin', name='userrole', create_type=True)
    enum_type.create(op.get_bind(), checkfirst=True)

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('role', enum_type, nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )

    # Create api_keys table
    op.create_table(
        'api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('key_hash', sa.String(), nullable=False),
        sa.Column('prefix', sa.String(8), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key_hash'),
    )


def downgrade() -> None:
    # Drop api_keys table
    op.drop_table('api_keys')

    # Drop users table
    op.drop_table('users')

    # Drop the UserRole enum type
    user_role_enum = postgresql.ENUM('viewer', 'analyst', 'admin', 'super_admin', name='userrole')
    user_role_enum.drop(op.get_bind(), checkfirst=True)
