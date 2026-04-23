"""chapters.first_approved_at: отметка первого approve главы.

Revision ID: 0007_chapter_first_approved
Revises: 0006_social
Create Date: 2026-04-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_chapter_first_approved"
down_revision: str | None = "0006_social"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chapters",
        sa.Column("first_approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill: уже approved главы помечаем текущим временем, чтобы они не
    # считались «новыми» при следующем approve.
    op.execute(
        "UPDATE chapters SET first_approved_at = COALESCE(updated_at, created_at) "
        "WHERE status = 'approved';"
    )


def downgrade() -> None:
    op.drop_column("chapters", "first_approved_at")
