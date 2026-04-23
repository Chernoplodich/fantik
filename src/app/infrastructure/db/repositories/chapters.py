"""ChapterRepository: реализация IChapterRepository."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.fanfics.ports import IChapterRepository
from app.domain.fanfics.entities import Chapter as ChapterEntity
from app.domain.fanfics.value_objects import FicStatus
from app.domain.shared.types import ChapterId, FanficId
from app.infrastructure.db.mappers.fanfic import (
    apply_chapter_to_model,
    chapter_to_domain,
    new_chapter_model,
)
from app.infrastructure.db.models.chapter import Chapter as ChapterModel


class ChapterRepository(IChapterRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, chapter_id: ChapterId) -> ChapterEntity | None:
        row = await self._s.get(ChapterModel, int(chapter_id))
        return chapter_to_domain(row) if row else None

    async def save(self, chapter: ChapterEntity) -> ChapterEntity:
        if int(chapter.id) == 0:
            m = new_chapter_model(chapter)
            self._s.add(m)
            await self._s.flush()
            chapter.id = ChapterId(int(m.id))
            if m.created_at is not None:
                chapter.created_at = m.created_at
            if m.updated_at is not None:
                chapter.updated_at = m.updated_at
        else:
            m = await self._s.get(ChapterModel, int(chapter.id))
            if m is None:
                m = new_chapter_model(chapter)
                m.id = int(chapter.id)
                self._s.add(m)
            else:
                apply_chapter_to_model(m, chapter)
            await self._s.flush()
        return chapter

    async def list_by_fic(self, fic_id: FanficId) -> list[ChapterEntity]:
        stmt = (
            select(ChapterModel)
            .where(ChapterModel.fic_id == int(fic_id))
            .order_by(ChapterModel.number.asc())
        )
        return [chapter_to_domain(r) for r in (await self._s.execute(stmt)).scalars()]

    async def list_by_fic_and_statuses(
        self, fic_id: FanficId, statuses: list[FicStatus]
    ) -> list[ChapterEntity]:
        if not statuses:
            return []
        stmt = (
            select(ChapterModel)
            .where(
                ChapterModel.fic_id == int(fic_id),
                ChapterModel.status.in_(statuses),
            )
            .order_by(ChapterModel.number.asc())
        )
        return [chapter_to_domain(r) for r in (await self._s.execute(stmt)).scalars()]

    async def delete(self, chapter_id: ChapterId) -> None:
        await self._s.execute(delete(ChapterModel).where(ChapterModel.id == int(chapter_id)))
        await self._s.flush()

    async def count_by_fic(self, fic_id: FanficId) -> int:
        stmt = select(func.count(ChapterModel.id)).where(ChapterModel.fic_id == int(fic_id))
        return int((await self._s.execute(stmt)).scalar_one())

    async def next_number(self, fic_id: FanficId) -> int:
        stmt = select(func.coalesce(func.max(ChapterModel.number), 0)).where(
            ChapterModel.fic_id == int(fic_id)
        )
        cur = int((await self._s.execute(stmt)).scalar_one())
        return cur + 1
