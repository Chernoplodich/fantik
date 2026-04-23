"""users.blocked_bot_at: отмечаем юзеров, заблокировавших бота через my_chat_member.

Revision ID: 0009_user_bot_block
Revises: 0008_broadcasts_and_views
Create Date: 2026-04-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_user_bot_block"
down_revision: str | None = "0008_broadcasts_and_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("blocked_bot_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Частичный индекс: только активные юзеры (без блока) — для сегмент-резолвера.
    op.execute(
        "CREATE INDEX ix_users_active_not_blocked "
        "ON users (id) WHERE blocked_bot_at IS NULL AND banned_at IS NULL;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_users_active_not_blocked;")
    op.drop_column("users", "blocked_bot_at")
