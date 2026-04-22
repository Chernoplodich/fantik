"""Use case: построить/перестроить страницы главы."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.fanfics.ports import IChapterRepository
from app.application.reading.ports import IChapterPagesRepository, IPageCache
from app.application.shared.ports import UnitOfWork
from app.core.errors import NotFoundError
from app.domain.fanfics.services.paginator import ChapterPaginator
from app.domain.shared.types import ChapterId


@dataclass(frozen=True, kw_only=True)
class PaginateChapterCommand:
    chapter_id: int


class PaginateChapterUseCase:
    """Идемпотентно: delete → paginate → save_bulk → invalidate cache.

    Пишет в БД, поэтому открывает UoW и коммитит перед инвалидацией кэша
    (иначе воркер сделает «лишнюю» работу, но ничего не сохранит).
    """

    def __init__(
        self,
        uow: UnitOfWork,
        chapters: IChapterRepository,
        pages_repo: IChapterPagesRepository,
        page_cache: IPageCache,
    ) -> None:
        self._uow = uow
        self._chapters = chapters
        self._pages = pages_repo
        self._cache = page_cache

    async def __call__(self, cmd: PaginateChapterCommand) -> int:
        """Вернуть количество построенных страниц."""
        ch_id = ChapterId(cmd.chapter_id)
        ch = await self._chapters.get(ch_id)
        if ch is None:
            raise NotFoundError("Глава не найдена.")

        pages = ChapterPaginator.paginate(ch.text, ch.entities)
        async with self._uow:
            await self._pages.delete_by_chapter(ch_id)
            await self._pages.save_bulk(ch_id, pages)
            await self._uow.commit()
        # Инвалидация кэша — ПОСЛЕ коммита. Иначе окажемся в окне, когда кэш
        # пуст, БД ещё не закоммичена, и читалка получит устаревшую страницу.
        await self._cache.invalidate_chapter(ch_id)
        return len(pages)
