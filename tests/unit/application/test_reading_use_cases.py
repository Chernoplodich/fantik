"""Unit-тесты Reading-use case'ов через фейки."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.reading.mark_completed import (
    MarkCompletedCommand,
    MarkCompletedUseCase,
)
from app.application.reading.paginate_chapter import (
    PaginateChapterCommand,
    PaginateChapterUseCase,
)
from app.application.reading.save_progress import (
    SaveProgressCommand,
    SaveProgressUseCase,
)
from app.application.reading.toggle_bookmark import (
    ToggleBookmarkCommand,
    ToggleBookmarkUseCase,
)
from app.application.reading.toggle_like import (
    ToggleLikeCommand,
    ToggleLikeUseCase,
)
from app.core.clock import FrozenClock
from app.core.errors import NotFoundError
from app.domain.fanfics.entities import Chapter, Fanfic
from app.domain.fanfics.value_objects import (
    ChapterNumber,
    ChapterTitle,
    FanficTitle,
    FicStatus,
    Summary,
)
from app.domain.shared.types import ChapterId, FandomId, FanficId, UserId
from tests.unit.application._fakes import (
    FakeChapters,
    FakeFanfics,
    FakeOutbox,
    FakeUow,
)
from tests.unit.application._reading_fakes import (
    FakeBookmarks,
    FakeChapterPages,
    FakeLikes,
    FakePageCache,
    FakeReadingProgress,
    FakeReadsCompleted,
    extend_with_counters,
)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(at=datetime(2026, 4, 22, 12, 0, 0, tzinfo=UTC))


def _make_approved_fic(*, fic_id: int = 1) -> Fanfic:
    fic = Fanfic.create_draft(
        author_id=UserId(99),
        title=FanficTitle("Test"),
        summary=Summary("Sum"),
        summary_entities=[],
        fandom_id=FandomId(1),
        age_rating_id=1,
        cover_file_id=None,
        cover_file_unique_id=None,
        now=datetime(2026, 4, 20, tzinfo=UTC),
    )
    fic.id = FanficId(fic_id)
    fic.status = FicStatus.APPROVED
    return fic


def _make_approved_chapter(
    *, chapter_id: int, fic_id: int, number: int, text: str = "Chapter text."
) -> Chapter:
    ch = Chapter.create_draft(
        fic_id=FanficId(fic_id),
        number=ChapterNumber(number),
        title=ChapterTitle(f"Chapter {number}"),
        text=text,
        entities=[],
        chars_count=len(text),
        now=datetime(2026, 4, 20, tzinfo=UTC),
    )
    ch.id = ChapterId(chapter_id)
    ch.status = FicStatus.APPROVED
    return ch


# ---------- ToggleLikeUseCase ----------


class _FakeSearchQueue:
    """Фейк `ISearchIndexQueue`: запоминает fic_id для последующих проверок."""

    def __init__(self) -> None:
        self.enqueued: list[int] = []
        self.debounced: list[int] = []

    async def enqueue(self, fic_id: int) -> None:
        self.enqueued.append(int(fic_id))

    async def enqueue_debounced(self, fic_id: int, ttl_s: int = 60) -> None:
        self.debounced.append(int(fic_id))


class TestToggleLike:
    async def test_first_call_inserts_and_increments(self, clock: FrozenClock) -> None:
        fanfics = extend_with_counters(FakeFanfics())
        await fanfics.save(_make_approved_fic())
        likes = FakeLikes()
        search_q = _FakeSearchQueue()
        uc = ToggleLikeUseCase(FakeUow(), fanfics, likes, search_q, clock)
        res = await uc(ToggleLikeCommand(user_id=5, fic_id=1))
        assert res.now_liked is True
        assert fanfics.likes_counts == {1: 1}
        assert await likes.exists(UserId(5), FanficId(1)) is True
        assert search_q.debounced == [1]

    async def test_second_call_removes_and_decrements(self, clock: FrozenClock) -> None:
        fanfics = extend_with_counters(FakeFanfics())
        await fanfics.save(_make_approved_fic())
        likes = FakeLikes()
        search_q = _FakeSearchQueue()
        uc = ToggleLikeUseCase(FakeUow(), fanfics, likes, search_q, clock)
        await uc(ToggleLikeCommand(user_id=5, fic_id=1))
        res = await uc(ToggleLikeCommand(user_id=5, fic_id=1))
        assert res.now_liked is False
        assert fanfics.likes_counts == {1: 0}
        assert search_q.debounced == [1, 1]

    async def test_rejects_non_approved_fic(self, clock: FrozenClock) -> None:
        fanfics = extend_with_counters(FakeFanfics())
        fic = _make_approved_fic()
        fic.status = FicStatus.DRAFT
        await fanfics.save(fic)
        uc = ToggleLikeUseCase(FakeUow(), fanfics, FakeLikes(), _FakeSearchQueue(), clock)
        with pytest.raises(NotFoundError):
            await uc(ToggleLikeCommand(user_id=5, fic_id=1))


# ---------- ToggleBookmarkUseCase ----------


class TestToggleBookmark:
    async def test_toggle(self, clock: FrozenClock) -> None:
        fanfics = extend_with_counters(FakeFanfics())
        await fanfics.save(_make_approved_fic())
        bm = FakeBookmarks()
        uc = ToggleBookmarkUseCase(FakeUow(), fanfics, bm, clock)
        r1 = await uc(ToggleBookmarkCommand(user_id=5, fic_id=1))
        r2 = await uc(ToggleBookmarkCommand(user_id=5, fic_id=1))
        assert r1.now_bookmarked is True
        assert r2.now_bookmarked is False


# ---------- SaveProgressUseCase ----------


class TestSaveProgress:
    """После отключения throttle use case ВСЕГДА сохраняет последнюю страницу.

    Регрессия: раньше первый-пишет-побеждает throttle отбрасывал последующие
    записи в пределах 5-сек окна, и «▶ Продолжить» показывал не ту страницу,
    на которой пользователь закончил читать.
    """

    async def test_consecutive_writes_all_succeed(self, clock: FrozenClock) -> None:
        progress = FakeReadingProgress()
        uc = SaveProgressUseCase(FakeUow(), progress, clock)

        ok1 = await uc(SaveProgressCommand(user_id=1, fic_id=2, chapter_id=3, page_no=1))
        ok2 = await uc(SaveProgressCommand(user_id=1, fic_id=2, chapter_id=3, page_no=2))
        ok3 = await uc(SaveProgressCommand(user_id=1, fic_id=2, chapter_id=3, page_no=3))
        assert ok1 is True and ok2 is True and ok3 is True
        row = await progress.get(UserId(1), FanficId(2))
        assert row is not None
        assert row.page_no == 3, "Должна остаться последняя страница"
        assert int(row.chapter_id) == 3

    async def test_chapter_change_writes_new_chapter(self, clock: FrozenClock) -> None:
        progress = FakeReadingProgress()
        uc = SaveProgressUseCase(FakeUow(), progress, clock)

        await uc(SaveProgressCommand(user_id=1, fic_id=2, chapter_id=10, page_no=1))
        await uc(SaveProgressCommand(user_id=1, fic_id=2, chapter_id=20, page_no=1))

        row = await progress.get(UserId(1), FanficId(2))
        assert row is not None
        assert int(row.chapter_id) == 20
        assert row.page_no == 1


# ---------- MarkCompletedUseCase ----------


class TestMarkCompleted:
    async def test_last_chapter_increments_fic_counter_once(self, clock: FrozenClock) -> None:
        fanfics = extend_with_counters(FakeFanfics())
        await fanfics.save(_make_approved_fic())
        chapters = FakeChapters()
        ch1 = _make_approved_chapter(chapter_id=10, fic_id=1, number=1)
        ch2 = _make_approved_chapter(chapter_id=20, fic_id=1, number=2)
        await chapters.save(ch1)
        await chapters.save(ch2)

        reads = FakeReadsCompleted()
        outbox = FakeOutbox()
        uc = MarkCompletedUseCase(FakeUow(), fanfics, chapters, reads, outbox, clock)

        # Первый раз — инкрементит
        r1 = await uc(MarkCompletedCommand(user_id=5, fic_id=1, chapter_id=20))
        assert r1.fic_completed is True
        assert fanfics.reads_counts[1] == 1
        assert outbox.events[-1][0] == "fanfic.read_completed"

        # Повторно — не инкрементит (идемпотентность)
        r2 = await uc(MarkCompletedCommand(user_id=5, fic_id=1, chapter_id=20))
        assert r2.fic_completed is False
        assert fanfics.reads_counts[1] == 1

    async def test_non_last_chapter_does_not_increment(self, clock: FrozenClock) -> None:
        fanfics = extend_with_counters(FakeFanfics())
        await fanfics.save(_make_approved_fic())
        chapters = FakeChapters()
        ch1 = _make_approved_chapter(chapter_id=10, fic_id=1, number=1)
        ch2 = _make_approved_chapter(chapter_id=20, fic_id=1, number=2)
        await chapters.save(ch1)
        await chapters.save(ch2)

        reads = FakeReadsCompleted()
        outbox = FakeOutbox()
        uc = MarkCompletedUseCase(FakeUow(), fanfics, chapters, reads, outbox, clock)
        res = await uc(MarkCompletedCommand(user_id=5, fic_id=1, chapter_id=10))
        assert res.fic_completed is False
        assert res.chapter_completed is True
        assert fanfics.reads_counts.get(1, 0) == 0


# ---------- PaginateChapterUseCase ----------


class TestPaginateChapter:
    async def test_delete_before_save_idempotent(self) -> None:
        chapters = FakeChapters()
        text = "Первая страница " * 400  # достаточно большая
        ch = _make_approved_chapter(chapter_id=10, fic_id=1, number=1, text=text)
        ch.entities = []
        ch.chars_count = len(text)
        await chapters.save(ch)

        pages_repo = FakeChapterPages()
        cache = FakePageCache()
        uc = PaginateChapterUseCase(FakeUow(), chapters, pages_repo, cache)

        pages1 = await uc(PaginateChapterCommand(chapter_id=10))
        pages2 = await uc(PaginateChapterCommand(chapter_id=10))

        assert pages1 == pages2
        assert pages_repo.delete_calls == [10, 10]
        # Второй save вставил столько же страниц, сколько первый (не дубли).
        assert pages_repo.save_calls[0] == (10, pages1)
        assert pages_repo.save_calls[1] == (10, pages2)
        # Кэш сбрасывался дважды.
        assert cache.invalidate_calls == [10, 10]

    async def test_missing_chapter_raises(self) -> None:
        chapters = FakeChapters()
        uc = PaginateChapterUseCase(FakeUow(), chapters, FakeChapterPages(), FakePageCache())
        with pytest.raises(NotFoundError):
            await uc(PaginateChapterCommand(chapter_id=999))

    async def test_commits_uow_and_invalidates_cache(self) -> None:
        """Регрессия на Bug #2: воркер должен коммитить транзакцию."""
        chapters = FakeChapters()
        ch = _make_approved_chapter(chapter_id=10, fic_id=1, number=1, text="A" * 10000)
        ch.entities = []
        ch.chars_count = 10000
        await chapters.save(ch)

        pages_repo = FakeChapterPages()
        cache = FakePageCache()
        uow = FakeUow()
        uc = PaginateChapterUseCase(uow, chapters, pages_repo, cache)
        pages_count = await uc(PaginateChapterCommand(chapter_id=10))

        assert pages_count > 0
        # Главное: коммит был.
        assert uow.committed is True
        # Страницы сохранены в fake-репо.
        assert await pages_repo.count_by_chapter(ChapterId(10)) == pages_count
        # Кэш инвалидирован.
        assert cache.invalidate_calls == [10]


# ---------- ReadPageUseCase: продолжить с произвольной страницы/главы ----------


class TestReadPageContinue:
    """Регрессия на Bug #3: кнопка 'Продолжить' работает с произвольным c/p."""

    async def test_can_read_arbitrary_page_of_arbitrary_chapter(self, clock: FrozenClock) -> None:
        from app.application.reading.read_page import ReadPageCommand, ReadPageUseCase

        fanfics = extend_with_counters(FakeFanfics())
        await fanfics.save(_make_approved_fic())
        chapters = FakeChapters()
        # Глава 1 (короткая, 1 стр.) + Глава 2 (длинная — несколько стр.)
        short = _make_approved_chapter(chapter_id=10, fic_id=1, number=1, text="Short")
        short.entities = []
        await chapters.save(short)
        long_text = "Word " * 2000
        longc = _make_approved_chapter(chapter_id=20, fic_id=1, number=2, text=long_text)
        longc.entities = []
        longc.chars_count = len(long_text)
        await chapters.save(longc)

        pages_repo = FakeChapterPages()
        cache = FakePageCache()
        bm = FakeBookmarks()
        likes = FakeLikes()
        reads = FakeReadsCompleted()
        uc = ReadPageUseCase(fanfics, chapters, pages_repo, cache, bm, likes, reads)

        # Открываем стр.2 главы 2 (как из «Продолжить»).
        result = await uc(ReadPageCommand(user_id=5, fic_id=1, chapter_id=20, page_no=2))
        assert result.page.page_no == 2
        assert result.chapter.id == 20
        assert result.total_pages >= 2
        assert result.total_chapters == 2
        assert result.is_last_chapter is True
