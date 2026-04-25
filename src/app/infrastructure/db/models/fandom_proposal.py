"""ORM-модель fandom_proposals — заявки пользователей на новый фандом."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.reference.value_objects import FandomProposalStatus
from app.infrastructure.db.base import Base


class FandomProposal(Base):
    __tablename__ = "fandom_proposals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    category_hint: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    requested_by: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[FandomProposalStatus] = mapped_column(
        Enum(
            FandomProposalStatus,
            name="fandom_proposal_status",
            native_enum=True,
            create_type=False,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=FandomProposalStatus.PENDING,
        server_default="pending",
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_fandom_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("fandoms.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
