"""ORM-модель fanfics."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.fanfics.value_objects import FicStatus
from app.infrastructure.db.base import Base


class Fanfic(Base):
    __tablename__ = "fanfics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    summary_entities: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    cover_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_file_unique_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    fandom_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("fandoms.id", ondelete="RESTRICT"), nullable=False
    )
    age_rating_id: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("age_ratings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[FicStatus] = mapped_column(
        Enum(
            FicStatus,
            name="fic_status",
            native_enum=True,
            create_type=False,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        default=FicStatus.DRAFT,
        server_default=FicStatus.DRAFT.value,
        nullable=False,
    )
    current_version_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("fanfic_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    chapters_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    chars_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    views_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    likes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    reads_completed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    first_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_edit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
