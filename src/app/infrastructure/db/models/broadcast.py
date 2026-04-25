"""ORM-модели broadcasts + broadcast_deliveries."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    PrimaryKeyConstraint,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.broadcasts.value_objects import BroadcastStatus, DeliveryStatus
from app.infrastructure.db.base import Base

_bc_status_enum = Enum(
    BroadcastStatus,
    name="bc_status",
    native_enum=True,
    create_type=False,
    values_callable=lambda enum_cls: [e.value for e in enum_cls],
)
_bcd_status_enum = Enum(
    DeliveryStatus,
    name="bcd_status",
    native_enum=True,
    create_type=False,
    values_callable=lambda enum_cls: [e.value for e in enum_cls],
)


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    keyboard: Mapped[list[list[dict[str, Any]]] | None] = mapped_column(JSONB, nullable=True)
    segment_spec: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[BroadcastStatus] = mapped_column(
        _bc_status_enum, nullable=False, default=BroadcastStatus.DRAFT, server_default="draft"
    )
    stats: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BroadcastDelivery(Base):
    __tablename__ = "broadcast_deliveries"
    __table_args__ = (
        PrimaryKeyConstraint("broadcast_id", "user_id", name="pk_broadcast_deliveries"),
    )

    broadcast_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("broadcasts.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[DeliveryStatus] = mapped_column(
        _bcd_status_enum,
        nullable=False,
        default=DeliveryStatus.PENDING,
        server_default="pending",
    )
    attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
