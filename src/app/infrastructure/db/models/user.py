"""ORM-модель users."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.users.value_objects import Role
from app.infrastructure.db.base import Base


class User(Base):
    __tablename__ = "users"

    # tg_id как PK — без суррогата
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow", nullable=False)

    role: Mapped[Role] = mapped_column(
        Enum(
            Role,
            name="user_role",
            native_enum=True,
            create_type=False,
            # ВАЖНО: без этого SQLAlchemy шлёт имя члена (ADMIN), а в PG ENUM значения строчные
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        default=Role.USER,
        server_default=Role.USER.value,
        nullable=False,
    )
    author_nick: Mapped[str | None] = mapped_column(String(32), nullable=True)
    utm_source_code_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("tracking_codes.id", ondelete="SET NULL"),
        nullable=True,
    )

    agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    banned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    banned_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # UNIQUE case-insensitive по нику
        Index(
            "uq_users_author_nick_lower",
            text("LOWER(author_nick)"),
            unique=True,
            postgresql_where=text("author_nick IS NOT NULL"),
        ),
        Index(
            "ix_users_role_staff",
            "role",
            postgresql_where=text("role IN ('moderator','admin')"),
        ),
        Index("ix_users_last_seen_at", "last_seen_at"),
        Index("ix_users_utm_source_code_id", "utm_source_code_id"),
    )
