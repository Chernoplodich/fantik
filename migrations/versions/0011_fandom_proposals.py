"""fandom_proposals: заявки пользователей на новый фандом.

Поток: автор → submit (status=pending) → админ → approve/reject.
Approve создаёт запись в fandoms (created_fandom_id зафиксирован для аудита).

Анти-дубль реализован partial unique index: один пользователь не может иметь
две открытые (pending) заявки с одинаковым названием.

Revision ID: 0011_fandom_proposals
Revises: 0010_fandoms_taxonomy_expand
Create Date: 2026-04-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_fandom_proposals"
down_revision: str | None = "0010_fandoms_taxonomy_expand"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE fandom_proposal_status AS ENUM ('pending', 'approved', 'rejected');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )

    status_enum = postgresql.ENUM(
        "pending",
        "approved",
        "rejected",
        name="fandom_proposal_status",
        create_type=False,
    )

    op.create_table(
        "fandom_proposals",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("category_hint", sa.String(32), nullable=False),
        sa.Column("comment", sa.String(500), nullable=True),
        sa.Column(
            "requested_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            status_enum,
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "reviewed_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_comment", sa.String(500), nullable=True),
        sa.Column(
            "created_fandom_id",
            sa.BigInteger(),
            sa.ForeignKey("fandoms.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index(
        "ix_fandom_proposals_status_created",
        "fandom_proposals",
        ["status", sa.text("created_at DESC")],
    )

    # Partial unique: один пользователь не может иметь два открытых дубля по имени.
    op.execute(
        "CREATE UNIQUE INDEX uq_fandom_proposals_open_per_user_name "
        "ON fandom_proposals (requested_by, LOWER(name)) "
        "WHERE status = 'pending';"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_fandom_proposals_open_per_user_name;")
    op.drop_index("ix_fandom_proposals_status_created", table_name="fandom_proposals")
    op.drop_table("fandom_proposals")
    op.execute("DROP TYPE IF EXISTS fandom_proposal_status;")
