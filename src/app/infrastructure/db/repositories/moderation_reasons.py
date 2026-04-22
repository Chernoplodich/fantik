"""ReasonRepository: причины отказа."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.moderation.ports import IReasonRepository
from app.domain.moderation.value_objects import RejectionReason
from app.domain.shared.types import ModerationReasonId
from app.infrastructure.db.mappers.moderation import reason_to_domain
from app.infrastructure.db.models.moderation_reason import (
    ModerationReason as ReasonModel,
)


class ReasonRepository(IReasonRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_active(self) -> list[RejectionReason]:
        stmt = (
            select(ReasonModel)
            .where(ReasonModel.active.is_(True))
            .order_by(ReasonModel.sort_order.asc(), ReasonModel.id.asc())
        )
        return [
            reason_to_domain(m) for m in (await self._s.execute(stmt)).scalars()
        ]

    async def get_by_ids(
        self, reason_ids: list[ModerationReasonId]
    ) -> list[RejectionReason]:
        if not reason_ids:
            return []
        stmt = (
            select(ReasonModel)
            .where(ReasonModel.id.in_([int(i) for i in reason_ids]))
            .order_by(ReasonModel.sort_order.asc(), ReasonModel.id.asc())
        )
        return [
            reason_to_domain(m) for m in (await self._s.execute(stmt)).scalars()
        ]
