"""ORM-модель tags — свободные теги автора с поддержкой merge."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, BigIntPkMixin


class Tag(BigIntPkMixin, Base):
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(
        Enum(
            "character",
            "theme",
            "warning",
            "freeform",
            name="tag_kind",
            native_enum=True,
        ),
        nullable=False,
    )
    usage_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    merged_into_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("tags.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_tags_kind_usage", "kind", "usage_count"),)
