"""ChapterPagesRepository: хранение страниц главы + идемпотентные bulk-вставки."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.reading.ports import IChapterPagesRepository
from app.domain.fanfics.services.paginator import Page
from app.domain.shared.types import ChapterId
from app.infrastructure.db.models.chapter_page import ChapterPage as ChapterPageModel


def _row_to_page(m: ChapterPageModel) -> Page:
    return Page(
        page_no=int(m.page_no),
        text=m.text,
        entities=list(m.entities or []),
        chars_count=int(m.chars_count),
    )


class ChapterPagesRepository(IChapterPagesRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, chapter_id: ChapterId, page_no: int) -> Page | None:
        stmt = select(ChapterPageModel).where(
            ChapterPageModel.chapter_id == int(chapter_id),
            ChapterPageModel.page_no == page_no,
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return _row_to_page(row) if row else None

    async def count_by_chapter(self, chapter_id: ChapterId) -> int:
        stmt = select(func.count(ChapterPageModel.id)).where(
            ChapterPageModel.chapter_id == int(chapter_id)
        )
        return int((await self._s.execute(stmt)).scalar_one())

    async def save_bulk(self, chapter_id: ChapterId, pages: list[Page]) -> None:
        if not pages:
            return
        values = [
            {
                "chapter_id": int(chapter_id),
                "page_no": p.page_no,
                "text": p.text,
                "entities": list(p.entities or []),
                "chars_count": p.chars_count,
            }
            for p in pages
        ]
        stmt = (
            pg_insert(ChapterPageModel)
            .values(values)
            .on_conflict_do_nothing(index_elements=["chapter_id", "page_no"])
        )
        await self._s.execute(stmt)
        await self._s.flush()

    async def delete_by_chapter(self, chapter_id: ChapterId) -> None:
        await self._s.execute(
            delete(ChapterPageModel).where(ChapterPageModel.chapter_id == int(chapter_id))
        )
        await self._s.flush()
