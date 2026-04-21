"""init: users, tracking, справочники (fandoms, age_ratings, tags) + сиды.

Revision ID: 0001_init
Revises:
Create Date: 2026-04-21
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_init"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------- ENUM-ы (идемпотентно через DO-блок: CREATE TYPE IF NOT EXISTS нет в PG) ----------
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE user_role AS ENUM ('user', 'moderator', 'admin');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE tracking_event_type AS ENUM
              ('start', 'register', 'first_read', 'first_publish', 'custom');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE tag_kind AS ENUM ('character', 'theme', 'warning', 'freeform');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """
    )

    # Ссылки на уже созданные ENUM-типы (native=True, не создаёт TYPE повторно).
    user_role_enum = postgresql.ENUM(
        "user", "moderator", "admin",
        name="user_role",
        create_type=False,
    )
    tag_kind_enum = postgresql.ENUM(
        "character", "theme", "warning", "freeform",
        name="tag_kind",
        create_type=False,
    )

    # ---------- age_ratings ----------
    op.create_table(
        "age_ratings",
        sa.Column("id", sa.SmallInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(512), nullable=False),
        sa.Column("min_age", sa.SmallInteger(), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.UniqueConstraint("code", name="uq_age_ratings_code"),
    )

    # ---------- fandoms ----------
    op.create_table(
        "fandoms",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.String(128)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("slug", name="uq_fandoms_slug"),
    )
    op.create_index("ix_fandoms_category", "fandoms", ["category"])
    op.execute("CREATE INDEX ix_fandoms_aliases_gin ON fandoms USING GIN (aliases);")

    # ---------- tracking_codes ----------
    op.create_table(
        "tracking_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(1024), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_tracking_codes_code"),
    )

    # ---------- users ----------
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=True),
        sa.Column("last_name", sa.String(128), nullable=True),
        sa.Column("language_code", sa.String(8), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Europe/Moscow"),
        sa.Column(
            "role",
            user_role_enum,
            nullable=False,
            server_default="user",
        ),
        sa.Column("author_nick", sa.String(32), nullable=True),
        sa.Column(
            "utm_source_code_id",
            sa.BigInteger(),
            sa.ForeignKey("tracking_codes.id", ondelete="SET NULL", name="fk_users_utm_source_code_id_tracking_codes"),
            nullable=True,
        ),
        sa.Column("agreed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("banned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("banned_reason", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_users_author_nick_lower ON users (LOWER(author_nick)) "
        "WHERE author_nick IS NOT NULL;"
    )
    op.execute(
        "CREATE INDEX ix_users_role_staff ON users (role) "
        "WHERE role IN ('moderator','admin');"
    )
    op.create_index("ix_users_last_seen_at", "users", ["last_seen_at"])
    op.create_index("ix_users_utm_source_code_id", "users", ["utm_source_code_id"])

    # FK tracking_codes.created_by → users.id (позже, т.к. users создан после)
    op.create_foreign_key(
        "fk_tracking_codes_created_by_users",
        "tracking_codes", "users",
        ["created_by"], ["id"],
        ondelete="SET NULL",
    )

    # ---------- tags ----------
    op.create_table(
        "tags",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column(
            "kind",
            tag_kind_enum,
            nullable=False,
        ),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "merged_into_id",
            sa.BigInteger(),
            sa.ForeignKey("tags.id", ondelete="SET NULL", name="fk_tags_merged_into_id_tags"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("slug", name="uq_tags_slug"),
    )
    op.create_index("ix_tags_kind_usage", "tags", ["kind", "usage_count"])

    # ---------- tracking_events (partitioned by RANGE(created_at)) ----------
    op.execute(
        """
        CREATE TABLE tracking_events (
            id BIGSERIAL NOT NULL,
            code_id BIGINT REFERENCES tracking_codes(id) ON DELETE SET NULL,
            user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
            event_type tracking_event_type NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT pk_tracking_events PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at);
        """
    )
    op.execute(
        "CREATE INDEX ix_tracking_events_code_type_time "
        "ON tracking_events (code_id, event_type, created_at);"
    )
    op.execute("CREATE INDEX ix_tracking_events_user ON tracking_events (user_id);")
    op.execute(
        "CREATE INDEX ix_tracking_events_created_at_brin "
        "ON tracking_events USING BRIN (created_at);"
    )

    # default-партиция, чтобы INSERT работал, пока ежемесячные партиции не созданы
    op.execute(
        """
        CREATE TABLE tracking_events_default
        PARTITION OF tracking_events DEFAULT;
        """
    )
    # начальные 3 месячные партиции (текущий + 2 вперёд)
    op.execute(
        """
        DO $$
        DECLARE
            start_month DATE := DATE_TRUNC('month', NOW())::DATE;
            d DATE;
            part_name TEXT;
        BEGIN
            FOR i IN 0..2 LOOP
                d := (start_month + (i || ' months')::INTERVAL)::DATE;
                part_name := 'tracking_events_y' || to_char(d, 'YYYY') || 'm' || to_char(d, 'MM');
                EXECUTE format(
                    'CREATE TABLE IF NOT EXISTS %I PARTITION OF tracking_events FOR VALUES FROM (%L) TO (%L);',
                    part_name, d, (d + INTERVAL '1 month')::DATE
                );
            END LOOP;
        END $$;
        """
    )

    # ---------- сиды ----------
    _seed_age_ratings()
    _seed_fandoms()


def downgrade() -> None:
    # сначала убираем FK, чтобы можно было дропнуть таблицы
    op.drop_constraint("fk_tracking_codes_created_by_users", "tracking_codes", type_="foreignkey")

    # tracking_events (партиции удаляются каскадно с родительской)
    op.execute("DROP TABLE IF EXISTS tracking_events CASCADE;")

    op.drop_index("ix_tags_kind_usage", table_name="tags")
    op.drop_table("tags")

    op.drop_index("ix_users_utm_source_code_id", table_name="users")
    op.drop_index("ix_users_last_seen_at", table_name="users")
    op.execute("DROP INDEX IF EXISTS ix_users_role_staff;")
    op.execute("DROP INDEX IF EXISTS uq_users_author_nick_lower;")
    op.drop_table("users")

    op.drop_table("tracking_codes")

    op.execute("DROP INDEX IF EXISTS ix_fandoms_aliases_gin;")
    op.drop_index("ix_fandoms_category", table_name="fandoms")
    op.drop_table("fandoms")

    op.drop_table("age_ratings")

    sa.Enum(name="tag_kind").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tracking_event_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)


# ---------- seeders ----------


def _seed_age_ratings() -> None:
    table = sa.table(
        "age_ratings",
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("min_age", sa.SmallInteger),
        sa.column("sort_order", sa.SmallInteger),
    )
    op.bulk_insert(
        table,
        [
            {
                "code": "G",
                "name": "General Audiences",
                "description": "Для любой аудитории.",
                "min_age": 0,
                "sort_order": 1,
            },
            {
                "code": "PG",
                "name": "Parental Guidance",
                "description": "Желательно присутствие взрослых.",
                "min_age": 6,
                "sort_order": 2,
            },
            {
                "code": "PG-13",
                "name": "Parents Strongly Cautioned",
                "description": "Не рекомендовано детям до 13.",
                "min_age": 13,
                "sort_order": 3,
            },
            {
                "code": "R",
                "name": "Restricted",
                "description": "Сцены насилия, обсценная лексика, откровенные темы.",
                "min_age": 16,
                "sort_order": 4,
            },
            {
                "code": "NC-17",
                "name": "Adults Only",
                "description": "Только для взрослых: откровенный контент.",
                "min_age": 18,
                "sort_order": 5,
            },
        ],
    )


def _seed_fandoms() -> None:
    table = sa.table(
        "fandoms",
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("category", sa.String),
        sa.column("aliases", postgresql.ARRAY(sa.String)),
        sa.column("active", sa.Boolean),
    )
    op.bulk_insert(
        table,
        [
            {
                "slug": "harry-potter",
                "name": "Гарри Поттер",
                "category": "books",
                "aliases": ["HP", "Harry Potter", "Поттериана", "Хогвартс"],
                "active": True,
            },
            {
                "slug": "lotr",
                "name": "Властелин колец",
                "category": "books",
                "aliases": ["LOTR", "Lord of the Rings", "Толкин"],
                "active": True,
            },
            {
                "slug": "marvel",
                "name": "Marvel Cinematic Universe",
                "category": "movies",
                "aliases": ["MCU", "Марвел", "Мстители"],
                "active": True,
            },
            {
                "slug": "witcher",
                "name": "Ведьмак",
                "category": "games",
                "aliases": ["Witcher", "Геральт", "Сапковский"],
                "active": True,
            },
            {
                "slug": "naruto",
                "name": "Наруто",
                "category": "anime",
                "aliases": ["Naruto"],
                "active": True,
            },
        ],
    )
