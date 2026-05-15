"""add organizations, org_id to users/engagements, position to users

Revision ID: a1b2c3d4e5f6
Revises: f3c9a82e1d47
Create Date: 2026-05-14

"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = "aac91bff9e86"
branch_labels = None
depends_on = None

DEFAULT_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.add_column("users", sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("users", sa.Column("position", sa.String(), nullable=True))
    op.create_index("ix_users_org_id", "users", ["org_id"])

    op.add_column("engagements", sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_engagements_org_id", "engagements", ["org_id"])

    op.create_foreign_key("fk_users_org_id", "users", "organizations", ["org_id"], ["id"])
    op.create_foreign_key("fk_engagements_org_id", "engagements", "organizations", ["org_id"], ["id"])

    # Backfill: put any existing users/engagements into a "Default" org
    conn = op.get_bind()
    user_count = conn.execute(sa.text("SELECT COUNT(*) FROM users")).scalar()
    if user_count > 0:
        conn.execute(
            sa.text(
                "INSERT INTO organizations (id, name, created_at) VALUES (:id, :name, :ts) "
                "ON CONFLICT (name) DO NOTHING"
            ),
            {"id": str(DEFAULT_ORG_ID), "name": "Default", "ts": datetime.utcnow()},
        )
        conn.execute(
            sa.text("UPDATE users SET org_id = :org_id WHERE org_id IS NULL"),
            {"org_id": str(DEFAULT_ORG_ID)},
        )
        conn.execute(
            sa.text("UPDATE engagements SET org_id = :org_id WHERE org_id IS NULL"),
            {"org_id": str(DEFAULT_ORG_ID)},
        )


def downgrade() -> None:
    op.drop_constraint("fk_engagements_org_id", "engagements", type_="foreignkey")
    op.drop_constraint("fk_users_org_id", "users", type_="foreignkey")
    op.drop_index("ix_engagements_org_id", "engagements")
    op.drop_column("engagements", "org_id")
    op.drop_index("ix_users_org_id", "users")
    op.drop_column("users", "position")
    op.drop_column("users", "org_id")
    op.drop_table("organizations")
