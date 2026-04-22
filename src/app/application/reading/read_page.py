"""Use case: получить страницу главы (с lazy-пагинацией и кэшом)."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.fanfics.ports import IChapterRepository, IFanficRepository
from app.application.reading.ports import (
    IBookmarksRepository,
    IChapterPagesRepository,
    ILikesRepository,
    IPageCache,
    IReadsCompletedRepository,
)
from app.core.errors import NotFoundError
from app.domain.fanfics.entities import Chapter, Fanfic
from app.domain.fanfics.services.paginator import ChapterPaginator, Page
from app.domain.fanfics.value_objects import FicStatus
from app.domain.shared.types import ChapterId, FanficId, UserId


@dataclass(frozen=True, kw_only=True)
class ReadPageCommand:
    user_id: int
    fic_id: int
    chapter_id: int
    page_no: int


@dataclass(frozen=True, kw_only=True)
class ReadPageResult:
    fic: Fanfic
    chapter: Chapter
    page: Page
    total_pages: int
    total_chapters: int
    is_last_chapter: bool
    is_last_page_in_chapter: bool
    is_last_page_of_fic: bool
    is_bookmarked: bool
    is_liked: bool
    already_completed: bool


class ReadPageUseCase:
    def __init__(
        self,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        pages_repo: IChapterPagesRepository,
        page_cache: IPageCache,
        bookmarks: IBookmarksRepository,
        likes: ILikesRepository,
        reads_completed: IReadsCompletedRepository,
    ) -> None:
        self._fanfics = fanfics
        self._chapters = chapters
        self._pages = pages_repo
        self._cache = page_cache
        self._bookmarks = bookmarks
        self._likes = likes
        self._reads_completed = reads_completed

    async def __call__(self, cmd: ReadPageCommand) -> ReadPageResult:
        fic_id = FanficId(cmd.fic_id)
        ch_id = ChapterId(cmd.chapter_id)
        user_id = UserId(cmd.user_id)

        fic = await self._fanfics.get(fic_id)
        if fic is None or fic.status != FicStatus.APPROVED:
            raise NotFoundError("Фик недоступен.")

        chapter = await self._chapters.get(ch_id)
        if chapter is None or chapter.fic_id != fic_id:
            raise NotFoundError("Глава не найдена.")
        if chapter.status != FicStatus.APPROVED:
            raise NotFoundError("Глава недоступна.")

        chapters = await self._chapters.list_by_fic(fic_id)
        approved = [c for c in chapters if c.status == FicStatus.APPROVED]
        approved.sort(key=lambda c: int(c.number))
        total_chapters = len(approved)
        is_last_chapter = bool(approved) and int(approved[-1].id) == int(chapter.id)

        page, total_pages = await self._get_page(chapter, cmd.page_no)
        is_last_page_in_chapter = cmd.page_no >= total_pages
        is_last_page_of_fic = is_last_chapter and is_last_page_in_chapter

        is_bookmarked = await self._bookmarks.exists(user_id, fic_id)
        is_liked = await self._likes.exists(user_id, fic_id)
        already_completed = (
            await self._reads_completed.exists(user_id, ch_id) if is_last_page_in_chapter else False
        )

        return ReadPageResult(
            fic=fic,
            chapter=chapter,
            page=page,
            total_pages=total_pages,
            total_chapters=total_chapters,
            is_last_chapter=is_last_chapter,
            is_last_page_in_chapter=is_last_page_in_chapter,
            is_last_page_of_fic=is_last_page_of_fic,
            is_bookmarked=is_bookmarked,
            is_liked=is_liked,
            already_completed=already_completed,
        )

    async def _get_page(self, chapter: Chapter, page_no: int) -> tuple[Page, int]:
        ch_id = ChapterId(int(chapter.id))

        # Fast path: кэш Redis.
        cached = await self._cache.get(ch_id, page_no)
        if cached is not None:
            total = await self._pages.count_by_chapter(ch_id)
            if total == 0:
                # Воркер ещё не отработал; total возьмём по in-memory пагинации.
                # Кэш уже отдал страницу — быстрый ответ, total вычислим один раз.
                return cached, self._count_pages_in_memory(chapter)
            return cached, total

        # Нет в кэше — смотрим DB.
        total = await self._pages.count_by_chapter(ch_id)
        if total > 0:
            if page_no < 1 or page_no > total:
                raise NotFoundError("Страница не найдена.")
            row = await self._pages.get(ch_id, page_no)
            if row is not None:
                await self._cache.set(ch_id, page_no, row)
                return row, total

        # Lazy-пагинация: воркер ещё не отработал ИЛИ страница пропала.
        # Пагинируем в памяти, кладём всё в кэш; запись в БД — забота воркера
        # `repaginate_chapter`. Не дублируем её в read-only use case.
        pages = ChapterPaginator.paginate(chapter.text, chapter.entities)
        if not pages:
            raise NotFoundError("Глава пуста.")
        if page_no < 1 or page_no > len(pages):
            raise NotFoundError("Страница не найдена.")
        # Прогреем кэш соседней и текущей страниц (одной транзакцией в Redis нельзя,
        # но несколько setex параллельно — ок).
        page = pages[page_no - 1]
        await self._cache.set(ch_id, page_no, page)
        return page, len(pages)

    @staticmethod
    def _count_pages_in_memory(chapter: Chapter) -> int:
        """Эвристика: сколько страниц в главе, считая в памяти.

        Вызывается только когда в БД нет строк, но Redis отдал страницу —
        значит воркер в процессе записи. Чтобы не соврать по `total`, считаем
        по актуальному тексту главы.
        """
        pages = ChapterPaginator.paginate(chapter.text, chapter.entities)
        return len(pages) or 1
