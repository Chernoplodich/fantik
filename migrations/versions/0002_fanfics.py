"""fanfics: fanfics, fanfic_tags, fanfic_versions, chapters, chapter_pages.

Revision ID: 0002_fanfics
Revises: 0001_init
Create Date: 2026-04-21
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_fanfics"
down_revision: str | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------- ENUM fic_status ----------
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE fic_status AS ENUM
              ('draft', 'pending', 'approved', 'rejected', 'revising', 'archived');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    fic_status_enum = postgresql.ENUM(
        "draft", "pending", "approved", "rejected", "revising", "archived",
        name="fic_status",
        create_type=False,
    )

    # ---------- fanfics ----------
    op.create_table(
        "fanfics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "author_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_fanfics_author_id_users"),
            nullable=False,
        ),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "summary_entities",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("cover_file_id", sa.Text(), nullable=True),
        sa.Column("cover_file_unique_id", sa.Text(), nullable=True),
        sa.Column(
            "fandom_id",
            sa.BigInteger(),
            sa.ForeignKey("fandoms.id", ondelete="RESTRICT", name="fk_fanfics_fandom_id_fandoms"),
            nullable=False,
        ),
        sa.Column(
            "age_rating_id",
            sa.SmallInteger(),
            sa.ForeignKey("age_ratings.id", ondelete="RESTRICT", name="fk_fanfics_age_rating_id_age_ratings"),
            nullable=False,
        ),
        sa.Column("status", fic_status_enum, nullable=False, server_default="draft"),
        sa.Column("current_version_id", sa.BigInteger(), nullable=True),
        sa.Column("chapters_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chars_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("views_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("likes_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reads_completed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_edit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_fanfics_author_status_updated",
        "fanfics",
        ["author_id", "status", sa.text("updated_at DESC")],
    )
    op.execute(
        "CREATE INDEX ix_fanfics_pending ON fanfics (status) WHERE status = 'pending';"
    )
    op.execute(
        "CREATE INDEX ix_fanfics_approved_new "
        "ON fanfics (first_published_at DESC) WHERE status = 'approved';"
    )
    op.execute(
        "CREATE INDEX ix_fanfics_approved_top "
        "ON fanfics (likes_count DESC) WHERE status = 'approved';"
    )
    op.execute(
        "CREATE INDEX ix_fanfics_fandom_approved "
        "ON fanfics (fandom_id) WHERE status = 'approved';"
    )
    op.execute(
        "CREATE INDEX ix_fanfics_age_rating_approved "
        "ON fanfics (age_rating_id) WHERE status = 'approved';"
    )
    op.create_index("ix_fanfics_author_created", "fanfics", ["author_id", "created_at"])

    # ---------- fanfic_versions ----------
    op.create_table(
        "fanfic_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "fic_id",
            sa.BigInteger(),
            sa.ForeignKey("fanfics.id", ondelete="CASCADE", name="fk_fanfic_versions_fic_id_fanfics"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "summary_entities",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "snapshot_chapters",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("fic_id", "version_no", name="uq_fanfic_versions_fic_id_version_no"),
    )
    op.create_index("ix_fanfic_versions_fic_id", "fanfic_versions", ["fic_id"])

    # теперь можно добавить FK fanfics.current_version_id → fanfic_versions.id
    op.create_foreign_key(
        "fk_fanfics_current_version_id_fanfic_versions",
        "fanfics",
        "fanfic_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---------- chapters ----------
    op.create_table(
        "chapters",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "fic_id",
            sa.BigInteger(),
            sa.ForeignKey("fanfics.id", ondelete="CASCADE", name="fk_chapters_fic_id_fanfics"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "entities",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("chars_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", fic_status_enum, nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("fic_id", "number", name="uq_chapters_fic_id_number"),
    )
    # tsvector GENERATED ALWAYS AS STORED — добавляем через op.execute
    op.execute(
        "ALTER TABLE chapters "
        "ADD COLUMN tsv_title tsvector "
        "GENERATED ALWAYS AS (to_tsvector('russian', coalesce(title, ''))) STORED;"
    )
    op.execute(
        "ALTER TABLE chapters "
        "ADD COLUMN tsv_text tsvector "
        "GENERATED ALWAYS AS (to_tsvector('russian', coalesce(text, ''))) STORED;"
    )
    op.create_index("ix_chapters_fic_id_number", "chapters", ["fic_id", "number"])
    op.execute("CREATE INDEX ix_chapters_tsv_title_gin ON chapters USING GIN (tsv_title);")
    op.execute("CREATE INDEX ix_chapters_tsv_text_gin ON chapters USING GIN (tsv_text);")
    op.execute(
        "CREATE INDEX ix_chapters_pending ON chapters (status) WHERE status = 'pending';"
    )

    # ---------- fanfic_tags (m:n) ----------
    op.create_table(
        "fanfic_tags",
        sa.Column(
            "fic_id",
            sa.BigInteger(),
            sa.ForeignKey("fanfics.id", ondelete="CASCADE", name="fk_fanfic_tags_fic_id_fanfics"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.BigInteger(),
            sa.ForeignKey("tags.id", ondelete="CASCADE", name="fk_fanfic_tags_tag_id_tags"),
            primary_key=True,
        ),
    )
    op.create_index("ix_fanfic_tags_tag_fic", "fanfic_tags", ["tag_id", "fic_id"])

    # ---------- chapter_pages (пустая схема; наполняется в этапе 3) ----------
    op.create_table(
        "chapter_pages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "chapter_id",
            sa.BigInteger(),
            sa.ForeignKey("chapters.id", ondelete="CASCADE", name="fk_chapter_pages_chapter_id_chapters"),
            nullable=False,
        ),
        sa.Column("page_no", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "entities",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("chars_count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("chapter_id", "page_no", name="uq_chapter_pages_chapter_id_page_no"),
    )
    op.create_index("ix_chapter_pages_chapter_page", "chapter_pages", ["chapter_id", "page_no"])


def downgrade() -> None:
    op.drop_index("ix_chapter_pages_chapter_page", table_name="chapter_pages")
    op.drop_table("chapter_pages")

    op.drop_index("ix_fanfic_tags_tag_fic", table_name="fanfic_tags")
    op.drop_table("fanfic_tags")

    op.execute("DROP INDEX IF EXISTS ix_chapters_pending;")
    op.execute("DROP INDEX IF EXISTS ix_chapters_tsv_text_gin;")
    op.execute("DROP INDEX IF EXISTS ix_chapters_tsv_title_gin;")
    op.drop_index("ix_chapters_fic_id_number", table_name="chapters")
    op.drop_table("chapters")

    op.drop_constraint(
        "fk_fanfics_current_version_id_fanfic_versions", "fanfics", type_="foreignkey"
    )
    op.drop_index("ix_fanfic_versions_fic_id", table_name="fanfic_versions")
    op.drop_table("fanfic_versions")

    op.drop_index("ix_fanfics_author_created", table_name="fanfics")
    op.execute("DROP INDEX IF EXISTS ix_fanfics_age_rating_approved;")
    op.execute("DROP INDEX IF EXISTS ix_fanfics_fandom_approved;")
    op.execute("DROP INDEX IF EXISTS ix_fanfics_approved_top;")
    op.execute("DROP INDEX IF EXISTS ix_fanfics_approved_new;")
    op.execute("DROP INDEX IF EXISTS ix_fanfics_pending;")
    op.drop_index("ix_fanfics_author_status_updated", table_name="fanfics")
    op.drop_table("fanfics")

    sa.Enum(name="fic_status").drop(op.get_bind(), checkfirst=True)
