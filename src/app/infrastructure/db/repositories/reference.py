"""ReferenceReader: чтение справочников fandoms и age_ratings."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fanfics.ports import (
    AgeRatingRef,
    FandomRef,
    IReferenceReader,
)
from app.domain.fanfics.value_objects import AgeRatingCode
from app.domain.shared.types import FandomId
from app.infrastructure.db.models.age_rating import AgeRating as AgeRatingModel
from app.infrastructure.db.models.fandom import Fandom as FandomModel


def _fandom_ref(m: FandomModel) -> FandomRef:
    return FandomRef(
        id=FandomId(m.id),
        slug=str(m.slug),
        name=str(m.name),
        category=str(m.category),
    )


def _age_rating_ref(m: AgeRatingModel) -> AgeRatingRef:
    return AgeRatingRef(
        id=int(m.id),
        code=AgeRatingCode(m.code),
        name=str(m.name),
        description=str(m.description),
        min_age=int(m.min_age),
        sort_order=int(m.sort_order),
    )


class ReferenceReader(IReferenceReader):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_fandoms_paginated(
        self, *, limit: int, offset: int, active_only: bool = True
    ) -> tuple[list[FandomRef], int]:
        total_stmt = select(func.count(FandomModel.id))
        main_stmt = select(FandomModel).order_by(FandomModel.name.asc())
        if active_only:
            total_stmt = total_stmt.where(FandomModel.active.is_(True))
            main_stmt = main_stmt.where(FandomModel.active.is_(True))
        total = int((await self._s.execute(total_stmt)).scalar_one())
        rows = (await self._s.execute(main_stmt.limit(limit).offset(offset))).scalars().all()
        return [_fandom_ref(m) for m in rows], total

    async def get_fandom(self, fandom_id: FandomId) -> FandomRef | None:
        m = await self._s.get(FandomModel, int(fandom_id))
        return _fandom_ref(m) if m else None

    async def list_age_ratings(self) -> list[AgeRatingRef]:
        stmt = select(AgeRatingModel).order_by(AgeRatingModel.sort_order.asc())
        return [_age_rating_ref(m) for m in (await self._s.execute(stmt)).scalars()]

    async def get_age_rating(self, rating_id: int) -> AgeRatingRef | None:
        m = await self._s.get(AgeRatingModel, int(rating_id))
        return _age_rating_ref(m) if m else None
