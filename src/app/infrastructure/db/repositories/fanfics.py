"""FanficRepository: реализация IFanficRepository."""

from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fanfics.ports import (
    FanficListItem,
    FanficWithChapters,
    IFanficRepository,
)
from app.domain.fanfics.entities import Fanfic as FanficEntity
from app.domain.fanfics.value_objects import FicStatus
from app.domain.shared.types import FanficId, UserId
from app.infrastructure.db.mappers.fanfic import (
    apply_fanfic_to_model,
    chapter_to_domain,
    fanfic_to_domain,
    new_fanfic_model,
)
from app.infrastructure.db.models.chapter import Chapter as ChapterModel
from app.infrastructure.db.models.fanfic import Fanfic as FanficModel


class FanficRepository(IFanficRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, fic_id: FanficId) -> FanficEntity | None:
        row = await self._s.get(FanficModel, int(fic_id))
        return fanfic_to_domain(row) if row else None

    async def get_with_chapters(
        self, fic_id: FanficId
    ) -> FanficWithChapters | None:
        m = await self._s.get(FanficModel, int(fic_id))
        if m is None:
            return None
        fic = fanfic_to_domain(m)
        stmt = (
            select(ChapterModel)
            .where(ChapterModel.fic_id == int(fic_id))
            .order_by(ChapterModel.number.asc())
        )
        chapters = [chapter_to_domain(r) for r in (await self._s.execute(stmt)).scalars()]
        return FanficWithChapters(fic=fic, chapters=chapters, tags=[])

    async def save(self, fic: FanficEntity) -> FanficEntity:
        if int(fic.id) == 0:
            m = new_fanfic_model(fic)
            self._s.add(m)
            await self._s.flush()
            # синхронизируем id обратно в агрегат
            fic.id = FanficId(int(m.id))
            if m.created_at is not None:
                fic.created_at = m.created_at
            if m.updated_at is not None:
                fic.updated_at = m.updated_at
        else:
            m = await self._s.get(FanficModel, int(fic.id))
            if m is None:
                m = new_fanfic_model(fic)
                m.id = int(fic.id)
                self._s.add(m)
            else:
                apply_fanfic_to_model(m, fic)
            await self._s.flush()
        return fic

    async def list_by_author_paginated(
        self, *, author_id: UserId, limit: int, offset: int
    ) -> tuple[list[FanficListItem], int]:
        total_stmt = select(func.count(FanficModel.id)).where(
            FanficModel.author_id == int(author_id),
            FanficModel.deleted_at.is_(None),
        )
        total = int((await self._s.execute(total_stmt)).scalar_one())

        stmt = (
            select(FanficModel)
            .where(
                FanficModel.author_id == int(author_id),
                FanficModel.deleted_at.is_(None),
            )
            .order_by(FanficModel.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        items = [
            FanficListItem(
                fic_id=FanficId(m.id),
                title=m.title,
                status=FicStatus(m.status),
                chapters_count=int(m.chapters_count),
                updated_at=m.updated_at,
            )
            for m in rows
        ]
        return items, total

    async def count_submitted_today(
        self, *, author_id: UserId, tz: str
    ) -> int:
        stmt = text(
            """
            SELECT COUNT(*) FROM fanfics
             WHERE author_id = :author_id
               AND created_at >= (DATE_TRUNC('day', NOW() AT TIME ZONE :tz) AT TIME ZONE :tz)
            """
        )
        result = await self._s.execute(stmt, {"author_id": int(author_id), "tz": tz})
        return int(result.scalar_one())
