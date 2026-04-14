"""add_poc_detail_to_findings

Revision ID: 3598619487a0
Revises: 214048a7e8e6
Create Date: 2026-04-13 21:48:33.120266

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3598619487a0'
down_revision: Union[str, None] = '214048a7e8e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('findings', sa.Column('poc_detail', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('findings', 'poc_detail')
