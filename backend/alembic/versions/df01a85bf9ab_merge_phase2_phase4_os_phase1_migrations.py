"""merge phase2 phase4 os_phase1 migrations

Revision ID: df01a85bf9ab
Revises: d4e5f6a7b8c9, e5f6a7b8c9d0, f6a7b8c9d0e1
Create Date: 2026-05-21 15:41:33.875920

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'df01a85bf9ab'
down_revision: Union[str, None] = ('d4e5f6a7b8c9', 'e5f6a7b8c9d0', 'f6a7b8c9d0e1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
