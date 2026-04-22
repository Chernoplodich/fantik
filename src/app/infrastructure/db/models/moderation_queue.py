"""ORM-модель moderation_queue."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.fanfics.value_objects import MqDecision, MqKind
from app.infrastructure.db.base import Base


class ModerationQueue(Base):
    __tablename__ = "moderation_queue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fic_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fanfics.id", ondelete="CASCADE"),
        nullable=False,
    )
    chapter_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("chapters.id", ondelete="CASCADE"),
        nullable=True,
    )
    kind: Mapped[MqKind] = mapped_column(
        Enum(
            MqKind,
            name="mq_kind",
            native_enum=True,
            create_type=False,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    submitted_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    locked_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision: Mapped[MqDecision | None] = mapped_column(
        Enum(
            MqDecision,
            name="mq_decision",
            native_enum=True,
            create_type=False,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=True,
    )
    decision_reason_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger),
        nullable=False,
        default=list,
        server_default="{}",
    )
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_comment_entities: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    decided_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
