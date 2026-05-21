"""cascade delete engagement children

Revision ID: a9f1c3e7b204
Revises: 791663b092f7
Create Date: 2026-05-19

Adds ON DELETE CASCADE to all FK columns that reference engagements.id:
  - findings.engagement_id
  - tasks.engagement_id
  - agents.engagement_id
  - knowledge_entries.engagement_id
  - engagement_events.engagement_id

Deleting an engagement now automatically removes all child rows at the
database level, preventing orphaned rows from accumulating.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9f1c3e7b204"
down_revision: str | None = "791663b092f7"
branch_labels = None
depends_on = None

# (table, constraint_name, fk_column, ref_table, ref_column)
_FK_UPDATES = [
    ("findings",          "findings_engagement_id_fkey",          "engagement_id", "engagements", "id"),
    ("tasks",             "tasks_engagement_id_fkey",             "engagement_id", "engagements", "id"),
    ("agents",            "agents_engagement_id_fkey",            "engagement_id", "engagements", "id"),
    ("knowledge_entries", "knowledge_entries_engagement_id_fkey", "engagement_id", "engagements", "id"),
    ("engagement_events", "engagement_events_engagement_id_fkey", "engagement_id", "engagements", "id"),
]


def upgrade() -> None:
    for table, constraint, col, ref_table, ref_col in _FK_UPDATES:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(
            constraint,
            table,
            ref_table,
            [col],
            [ref_col],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    for table, constraint, col, ref_table, ref_col in _FK_UPDATES:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(
            constraint,
            table,
            ref_table,
            [col],
            [ref_col],
        )
