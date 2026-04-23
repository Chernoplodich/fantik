"""broadcasts + broadcast_deliveries (hash-partitioned) + materialized views.

Revision ID: 0008_broadcasts_and_views
Revises: 0007_chapter_first_approved
Create Date: 2026-04-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_broadcasts_and_views"
down_revision: str | None = "0007_chapter_first_approved"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_PARTITIONS = 16


def upgrade() -> None:
    # ---------- ENUMы ----------
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE bc_status AS ENUM
              ('draft', 'scheduled', 'running', 'finished', 'cancelled', 'failed');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE bcd_status AS ENUM ('pending', 'sent', 'failed', 'blocked');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    bc_status_enum = postgresql.ENUM(
        "draft", "scheduled", "running", "finished", "cancelled", "failed",
        name="bc_status",
        create_type=False,
    )

    # ---------- broadcasts ----------
    op.create_table(
        "broadcasts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="RESTRICT", name="fk_broadcasts_created_by_users"),
            nullable=False,
        ),
        sa.Column("source_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("source_message_id", sa.BigInteger(), nullable=False),
        sa.Column("keyboard", postgresql.JSONB, nullable=True),
        sa.Column(
            "segment_spec",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            bc_status_enum,
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column(
            "stats",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_broadcasts_status_scheduled",
        "broadcasts",
        ["status", "scheduled_at"],
    )
    op.create_index(
        "ix_broadcasts_created_by_created_at",
        "broadcasts",
        ["created_by", sa.text("created_at DESC")],
    )

    # ---------- broadcast_deliveries (HASH partitioned 16) ----------
    op.execute(
        """
        CREATE TABLE broadcast_deliveries (
            broadcast_id BIGINT NOT NULL
              REFERENCES broadcasts(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL
              REFERENCES users(id) ON DELETE CASCADE,
            status bcd_status NOT NULL DEFAULT 'pending',
            attempts SMALLINT NOT NULL DEFAULT 0,
            error_code TEXT NULL,
            sent_at TIMESTAMPTZ NULL,
            CONSTRAINT pk_broadcast_deliveries PRIMARY KEY (broadcast_id, user_id)
        ) PARTITION BY HASH (broadcast_id);
        """
    )
    for i in range(_PARTITIONS):
        op.execute(
            f"""
            CREATE TABLE broadcast_deliveries_p{i}
            PARTITION OF broadcast_deliveries
            FOR VALUES WITH (MODULUS {_PARTITIONS}, REMAINDER {i});
            """
        )
    op.execute(
        "CREATE INDEX ix_broadcast_deliveries_broadcast_status "
        "ON broadcast_deliveries (broadcast_id, status);"
    )
    op.execute(
        "CREATE INDEX ix_broadcast_deliveries_pending "
        "ON broadcast_deliveries (broadcast_id) WHERE status = 'pending';"
    )

    # ---------- materialized views ----------
    # mv_daily_activity: дневные агрегаты по tracking_events.
    op.execute(
        """
        CREATE MATERIALIZED VIEW mv_daily_activity AS
        SELECT
          date_trunc('day', created_at AT TIME ZONE 'UTC')::date AS day,
          count(*) FILTER (WHERE event_type = 'start')          AS starts,
          count(*) FILTER (WHERE event_type = 'register')       AS registers,
          count(*) FILTER (WHERE event_type = 'first_read')     AS first_reads,
          count(*) FILTER (WHERE event_type = 'first_publish')  AS first_publishes
        FROM tracking_events
        GROUP BY 1
        WITH DATA;
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_mv_daily_activity_day ON mv_daily_activity (day);"
    )

    # mv_top_fandoms_7d: топ фандомов по новым публикациям за 7 дней.
    op.execute(
        """
        CREATE MATERIALIZED VIEW mv_top_fandoms_7d AS
        SELECT
          f.fandom_id,
          fd.name AS fandom_name,
          count(*) AS new_fics_7d
        FROM fanfics f
        JOIN fandoms fd ON fd.id = f.fandom_id
        WHERE f.status = 'approved'
          AND f.first_published_at IS NOT NULL
          AND f.first_published_at > now() - interval '7 days'
        GROUP BY f.fandom_id, fd.name
        WITH DATA;
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_mv_top_fandoms_7d_fandom ON mv_top_fandoms_7d (fandom_id);"
    )

    # mv_author_stats: агрегаты по автору.
    op.execute(
        """
        CREATE MATERIALIZED VIEW mv_author_stats AS
        SELECT
          f.author_id,
          count(*) AS fics_count,
          COALESCE(sum(f.likes_count), 0)::bigint AS likes_sum,
          COALESCE(sum(f.reads_completed_count), 0)::bigint AS reads_completed_sum,
          max(f.first_published_at) AS last_published_at
        FROM fanfics f
        WHERE f.status = 'approved'
        GROUP BY f.author_id
        WITH DATA;
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_mv_author_stats_author ON mv_author_stats (author_id);"
    )

    # mv_moderator_load: нагрузка на модератора по дням.
    op.execute(
        """
        CREATE MATERIALIZED VIEW mv_moderator_load AS
        SELECT
          mq.decided_by AS moderator_id,
          date_trunc('day', mq.decided_at AT TIME ZONE 'UTC')::date AS day,
          count(*) AS decisions_total,
          count(*) FILTER (WHERE mq.decision = 'approved') AS approved_count,
          count(*) FILTER (WHERE mq.decision = 'rejected') AS rejected_count,
          COALESCE(
            avg(EXTRACT(EPOCH FROM (mq.decided_at - mq.submitted_at))),
            0
          )::double precision AS avg_latency_seconds
        FROM moderation_queue mq
        WHERE mq.decided_at IS NOT NULL
          AND mq.decided_by IS NOT NULL
        GROUP BY mq.decided_by, 2
        WITH DATA;
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_mv_moderator_load_mod_day "
        "ON mv_moderator_load (moderator_id, day);"
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_moderator_load;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_author_stats;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_top_fandoms_7d;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_daily_activity;")

    # Партиции удалятся каскадно вместе с родителем.
    op.execute("DROP TABLE IF EXISTS broadcast_deliveries CASCADE;")

    op.drop_index("ix_broadcasts_created_by_created_at", table_name="broadcasts")
    op.drop_index("ix_broadcasts_status_scheduled", table_name="broadcasts")
    op.drop_table("broadcasts")

    sa.Enum(name="bcd_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="bc_status").drop(op.get_bind(), checkfirst=True)
