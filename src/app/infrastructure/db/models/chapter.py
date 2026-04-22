"""ORM-модель chapters."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.fanfics.value_objects import FicStatus
from app.infrastructure.db.base import Base


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fic_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fanfics.id", ondelete="CASCADE"),
        nullable=False,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    entities: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    chars_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
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

    # Генерируемые STORED-колонки. SQL-выражение уже создано миграцией через op.execute,
    # здесь Computed(..., persisted=True) сообщает SQLAlchemy «не писать сюда INSERT/UPDATE».
    tsv_title: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('russian', coalesce(title, ''))", persisted=True),
        deferred=True,
        nullable=True,
    )
    tsv_text: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('russian', coalesce(text, ''))", persisted=True),
        deferred=True,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
