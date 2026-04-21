"""ORM-модель fandoms — справочник фандомов (редактируется админом)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, BigIntPkMixin


class Fandom(BigIntPkMixin, Base):
    __tablename__ = "fandoms"

    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)  # books/movies/games/...
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(String(128)), default=list, server_default="{}", nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_fandoms_category", "category"),
        # GIN на aliases создаётся в миграции явно
    )
