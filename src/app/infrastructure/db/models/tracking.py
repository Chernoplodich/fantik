"""ORM-модели трекинга. tracking_events — партиционированная по месяцам."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.tracking.value_objects import TrackingEventType
from app.infrastructure.db.base import Base, BigIntPkMixin


class TrackingCode(BigIntPkMixin, Base):
    __tablename__ = "tracking_codes"

    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TrackingEvent(Base):
    """Партиционированная таблица по created_at (месяцы).

    Первичный ключ (id, created_at) — ограничение PostgreSQL для партиционированных таблиц.
    """

    __tablename__ = "tracking_events"

    id: Mapped[int] = mapped_column(BigInteger, autoincrement=True, nullable=False)
    code_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("tracking_codes.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[TrackingEventType] = mapped_column(
        Enum(
            TrackingEventType,
            name="tracking_event_type",
            native_enum=True,
            create_type=False,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", "created_at", name="pk_tracking_events"),
        Index("ix_tracking_events_code_type_time", "code_id", "event_type", "created_at"),
        Index("ix_tracking_events_user", "user_id"),
        # BRIN на created_at создаётся в миграции явно (SQLAlchemy не имеет типа BRIN из коробки).
        {"postgresql_partition_by": "RANGE (created_at)"},
    )
