"""ORM-модель fanfic_tags (m:n)."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class FanficTag(Base):
    __tablename__ = "fanfic_tags"

    fic_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fanfics.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
