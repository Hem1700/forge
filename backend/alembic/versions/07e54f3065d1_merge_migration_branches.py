"""merge migration branches

Revision ID: 07e54f3065d1
Revises: a2b3c4d5e6f7, c3d4e5f6a7b8
Create Date: 2026-05-29 19:27:33.221034

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '07e54f3065d1'
down_revision: Union[str, None] = ('a2b3c4d5e6f7', 'c3d4e5f6a7b8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
