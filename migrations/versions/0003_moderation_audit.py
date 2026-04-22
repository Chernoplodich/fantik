"""moderation: moderation_queue, moderation_reasons (+seed 7), audit_log, outbox.

Revision ID: 0003_moderation_audit
Revises: 0002_fanfics
Create Date: 2026-04-21
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_moderation_audit"
down_revision: str | None = "0002_fanfics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------- ENUMы ----------
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE mq_kind AS ENUM
              ('fic_first_publish', 'fic_edit', 'chapter_add', 'chapter_edit');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE mq_decision AS ENUM ('approved', 'rejected');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    mq_kind_enum = postgresql.ENUM(
        "fic_first_publish", "fic_edit", "chapter_add", "chapter_edit",
        name="mq_kind",
        create_type=False,
    )
    mq_decision_enum = postgresql.ENUM(
        "approved", "rejected",
        name="mq_decision",
        create_type=False,
    )

    # ---------- moderation_reasons ----------
    op.create_table(
        "moderation_reasons",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("code", name="uq_moderation_reasons_code"),
    )
    _seed_moderation_reasons()

    # ---------- moderation_queue ----------
    op.create_table(
        "moderation_queue",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "fic_id",
            sa.BigInteger(),
            sa.ForeignKey("fanfics.id", ondelete="CASCADE", name="fk_moderation_queue_fic_id_fanfics"),
            nullable=False,
        ),
        sa.Column(
            "chapter_id",
            sa.BigInteger(),
            sa.ForeignKey("chapters.id", ondelete="CASCADE", name="fk_moderation_queue_chapter_id_chapters"),
            nullable=True,
        ),
        sa.Column("kind", mq_kind_enum, nullable=False),
        sa.Column(
            "submitted_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_moderation_queue_submitted_by_users"),
            nullable=False,
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "locked_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_moderation_queue_locked_by_users"),
            nullable=True,
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision", mq_decision_enum, nullable=True),
        sa.Column(
            "decision_reason_ids",
            postgresql.ARRAY(sa.BigInteger()),
            nullable=False,
            server_default=sa.text("'{}'::bigint[]"),
        ),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column(
            "decision_comment_entities",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "decided_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_moderation_queue_decided_by_users"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Частичный индекс: горячий набор = открытые, не отменённые.
    # `now()` не IMMUTABLE, потому фильтр по locked_until остаётся в WHERE запроса.
    op.execute(
        "CREATE INDEX ix_moderation_queue_open_submitted_at "
        "ON moderation_queue (submitted_at) "
        "WHERE decision IS NULL AND cancelled_at IS NULL;"
    )
    op.create_index(
        "ix_moderation_queue_locked_by_decided_at",
        "moderation_queue",
        ["locked_by", sa.text("decided_at DESC")],
    )
    op.create_index(
        "ix_moderation_queue_fic_submitted",
        "moderation_queue",
        ["fic_id", sa.text("submitted_at DESC")],
    )

    # ---------- audit_log (простая таблица; партиционирование — этап 7) ----------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "actor_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_audit_log_actor_id_users"),
            nullable=True,
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=True),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE INDEX ix_audit_log_created_at_brin "
        "ON audit_log USING BRIN (created_at);"
    )
    op.create_index(
        "ix_audit_log_actor_created",
        "audit_log",
        ["actor_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_audit_log_target",
        "audit_log",
        ["target_type", "target_id", sa.text("created_at DESC")],
    )

    # ---------- outbox ----------
    op.create_table(
        "outbox",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "CREATE INDEX ix_outbox_unpublished ON outbox (id) WHERE published_at IS NULL;"
    )
    op.create_index("ix_outbox_event_type", "outbox", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_outbox_event_type", table_name="outbox")
    op.execute("DROP INDEX IF EXISTS ix_outbox_unpublished;")
    op.drop_table("outbox")

    op.drop_index("ix_audit_log_target", table_name="audit_log")
    op.drop_index("ix_audit_log_actor_created", table_name="audit_log")
    op.execute("DROP INDEX IF EXISTS ix_audit_log_created_at_brin;")
    op.drop_table("audit_log")

    op.drop_index("ix_moderation_queue_fic_submitted", table_name="moderation_queue")
    op.drop_index(
        "ix_moderation_queue_locked_by_decided_at", table_name="moderation_queue"
    )
    op.execute("DROP INDEX IF EXISTS ix_moderation_queue_open_submitted_at;")
    op.drop_table("moderation_queue")

    op.drop_table("moderation_reasons")

    sa.Enum(name="mq_decision").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="mq_kind").drop(op.get_bind(), checkfirst=True)


def _seed_moderation_reasons() -> None:
    table = sa.table(
        "moderation_reasons",
        sa.column("code", sa.String),
        sa.column("title", sa.String),
        sa.column("description", sa.Text),
        sa.column("active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(
        table,
        [
            {
                "code": "RATING_MISMATCH",
                "title": "Неверный возрастной рейтинг",
                "description": (
                    "Контент не соответствует заявленному рейтингу. "
                    "Повысь рейтинг или убери сцены."
                ),
                "active": True,
                "sort_order": 10,
            },
            {
                "code": "PLAGIARISM",
                "title": "Плагиат",
                "description": (
                    "Текст частично/полностью скопирован из другого источника."
                ),
                "active": True,
                "sort_order": 20,
            },
            {
                "code": "LOW_QUALITY",
                "title": "Низкое качество",
                "description": (
                    "Много орфографических/пунктуационных ошибок, "
                    "текст сложно читать."
                ),
                "active": True,
                "sort_order": 30,
            },
            {
                "code": "NO_FANDOM",
                "title": "Не фанфик",
                "description": (
                    "Это оригинальное произведение, а платформа — "
                    "только для работ по существующим вселенным."
                ),
                "active": True,
                "sort_order": 40,
            },
            {
                "code": "INVALID_FORMAT",
                "title": "Проблемы с форматированием",
                "description": (
                    "Пустые строки, битые спойлеры, перепутано форматирование."
                ),
                "active": True,
                "sort_order": 50,
            },
            {
                "code": "WRONG_TAGS",
                "title": "Неверные теги",
                "description": "Теги не соответствуют содержимому.",
                "active": True,
                "sort_order": 60,
            },
            {
                "code": "RULES_VIOLATION",
                "title": "Нарушение правил",
                "description": "См. /rules — укажи пункт в комментарии.",
                "active": True,
                "sort_order": 70,
            },
        ],
    )
