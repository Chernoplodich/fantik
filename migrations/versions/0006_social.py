"""social: subscriptions, reports, notifications.

Revision ID: 0006_social
Revises: 0005_reading
Create Date: 2026-04-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_social"
down_revision: str | None = "0005_reading"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------- ENUMы ----------
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE report_target AS ENUM ('fanfic', 'chapter', 'user', 'comment');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE report_status AS ENUM ('open', 'dismissed', 'actioned');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    report_target_enum = postgresql.ENUM(
        "fanfic", "chapter", "user", "comment",
        name="report_target",
        create_type=False,
    )
    report_status_enum = postgresql.ENUM(
        "open", "dismissed", "actioned",
        name="report_status",
        create_type=False,
    )

    # ---------- subscriptions (подписчик → автор) ----------
    op.create_table(
        "subscriptions",
        sa.Column(
            "subscriber_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "users.id", ondelete="CASCADE", name="fk_subscriptions_subscriber_id_users"
            ),
            primary_key=True,
        ),
        sa.Column(
            "author_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "users.id", ondelete="CASCADE", name="fk_subscriptions_author_id_users"
            ),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "subscriber_id <> author_id", name="ck_subscriptions_not_self"
        ),
    )
    op.create_index("ix_subscriptions_author_id", "subscriptions", ["author_id"])
    op.create_index(
        "ix_subscriptions_subscriber_created",
        "subscriptions",
        ["subscriber_id", sa.text("created_at DESC")],
    )

    # ---------- reports ----------
    op.create_table(
        "reports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "reporter_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "users.id", ondelete="CASCADE", name="fk_reports_reporter_id_users"
            ),
            nullable=False,
        ),
        sa.Column("target_type", report_target_enum, nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column(
            "text_entities",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "status",
            report_status_enum,
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column(
            "handled_by",
            sa.BigInteger(),
            sa.ForeignKey(
                "users.id", ondelete="SET NULL", name="fk_reports_handled_by_users"
            ),
            nullable=True,
        ),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handler_comment", sa.Text(), nullable=True),
        sa.Column(
            "notify_reporter",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Частичный индекс: открытые жалобы на конкретную цель — для анти-дубля и сводных
    # выборок (нет дубля на ту же цель от того же репортера).
    op.execute(
        "CREATE INDEX ix_reports_open_target "
        "ON reports (target_type, target_id) "
        "WHERE status = 'open';"
    )
    # Очередь «Жалобы» модератора (open, по времени).
    op.execute(
        "CREATE INDEX ix_reports_open_created "
        "ON reports (created_at) "
        "WHERE status = 'open';"
    )
    op.create_index(
        "ix_reports_reporter_created",
        "reports",
        ["reporter_id", sa.text("created_at DESC")],
    )

    # ---------- notifications ----------
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "users.id", ondelete="CASCADE", name="fk_notifications_user_id_users"
            ),
            nullable=False,
        ),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Частичный индекс «не отправленные» — на случай пересыла при рестарте.
    op.execute(
        "CREATE INDEX ix_notifications_unsent "
        "ON notifications (user_id, created_at) "
        "WHERE sent_at IS NULL;"
    )
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.execute("DROP INDEX IF EXISTS ix_notifications_unsent;")
    op.drop_table("notifications")

    op.drop_index("ix_reports_reporter_created", table_name="reports")
    op.execute("DROP INDEX IF EXISTS ix_reports_open_created;")
    op.execute("DROP INDEX IF EXISTS ix_reports_open_target;")
    op.drop_table("reports")

    op.drop_index("ix_subscriptions_subscriber_created", table_name="subscriptions")
    op.drop_index("ix_subscriptions_author_id", table_name="subscriptions")
    op.drop_table("subscriptions")

    sa.Enum(name="report_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="report_target").drop(op.get_bind(), checkfirst=True)
