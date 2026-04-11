"""add_target_type_and_path

Revision ID: 65e1475be1be
Revises: 4d51f93d0ea5
Create Date: 2026-04-10 22:17:16.631722

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '65e1475be1be'
down_revision: Union[str, None] = '4d51f93d0ea5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add target_type with a server_default so existing rows backfill to "web",
    # then drop the default so future inserts must be explicit (matches model).
    op.add_column(
        'engagements',
        sa.Column('target_type', sa.String(), nullable=False, server_default='web'),
    )
    op.alter_column('engagements', 'target_type', server_default=None)
    op.add_column('engagements', sa.Column('target_path', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('engagements', 'target_path')
    op.drop_column('engagements', 'target_type')
