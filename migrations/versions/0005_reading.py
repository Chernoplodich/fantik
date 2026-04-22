"""reading: bookmarks, likes, reads_completed, reading_progress.

Revision ID: 0005_reading
Revises: 0004_more_fandoms
Create Date: 2026-04-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_reading"
down_revision: str | None = "0004_more_fandoms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------- bookmarks ----------
    op.create_table(
        "bookmarks",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_bookmarks_user_id_users"),
            primary_key=True,
        ),
        sa.Column(
            "fic_id",
            sa.BigInteger(),
            sa.ForeignKey("fanfics.id", ondelete="CASCADE", name="fk_bookmarks_fic_id_fanfics"),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_bookmarks_fic_id", "bookmarks", ["fic_id"])
    op.create_index(
        "ix_bookmarks_user_created",
        "bookmarks",
        ["user_id", sa.text("created_at DESC")],
    )

    # ---------- likes ----------
    # Счётчик fanfics.likes_count правит use case atomic UPDATE — не триггером.
    op.create_table(
        "likes",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_likes_user_id_users"),
            primary_key=True,
        ),
        sa.Column(
            "fic_id",
            sa.BigInteger(),
            sa.ForeignKey("fanfics.id", ondelete="CASCADE", name="fk_likes_fic_id_fanfics"),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_likes_fic_id", "likes", ["fic_id"])
    op.create_index(
        "ix_likes_user_created",
        "likes",
        ["user_id", sa.text("created_at DESC")],
    )

    # ---------- reads_completed ----------
    # По главе: пометка «эту главу дочитал». Флаг «дочитал фик» = есть запись по последней главе.
    op.create_table(
        "reads_completed",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "users.id", ondelete="CASCADE", name="fk_reads_completed_user_id_users"
            ),
            primary_key=True,
        ),
        sa.Column(
            "chapter_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "chapters.id",
                ondelete="CASCADE",
                name="fk_reads_completed_chapter_id_chapters",
            ),
            primary_key=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_reads_completed_chapter_id", "reads_completed", ["chapter_id"])

    # ---------- reading_progress ----------
    # Одна запись на пару (user_id, fic_id) — курсор чтения.
    op.create_table(
        "reading_progress",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "users.id", ondelete="CASCADE", name="fk_reading_progress_user_id_users"
            ),
            primary_key=True,
        ),
        sa.Column(
            "fic_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "fanfics.id",
                ondelete="CASCADE",
                name="fk_reading_progress_fic_id_fanfics",
            ),
            primary_key=True,
        ),
        sa.Column(
            "chapter_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "chapters.id",
                ondelete="CASCADE",
                name="fk_reading_progress_chapter_id_chapters",
            ),
            nullable=False,
        ),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_reading_progress_user_updated",
        "reading_progress",
        ["user_id", sa.text("updated_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reading_progress_user_updated", table_name="reading_progress"
    )
    op.drop_table("reading_progress")

    op.drop_index("ix_reads_completed_chapter_id", table_name="reads_completed")
    op.drop_table("reads_completed")

    op.drop_index("ix_likes_user_created", table_name="likes")
    op.drop_index("ix_likes_fic_id", table_name="likes")
    op.drop_table("likes")

    op.drop_index("ix_bookmarks_user_created", table_name="bookmarks")
    op.drop_index("ix_bookmarks_fic_id", table_name="bookmarks")
    op.drop_table("bookmarks")
