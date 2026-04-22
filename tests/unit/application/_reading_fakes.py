"""Фейковые реализации Reading-портов для unit-тестов."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.application.reading.ports import (
    FeedItem,
    IBookmarksRepository,
    IChapterPagesRepository,
    IFanficFeedReader,
    ILikesRepository,
    IPageCache,
    IProgressThrottle,
    IReadingProgressRepository,
    IReadsCompletedRepository,
    IRepaginationQueue,
    ReadingProgressDTO,
)
from app.domain.fanfics.services.paginator import Page
from app.domain.shared.types import ChapterId, FandomId, FanficId, UserId


class FakeBookmarks(IBookmarksRepository):
    def __init__(self) -> None:
        self._set: set[tuple[int, int]] = set()
        self._order: list[tuple[int, FanficId, datetime]] = []

    async def exists(self, user_id: UserId, fic_id: FanficId) -> bool:
        return (int(user_id), int(fic_id)) in self._set

    async def add(self, user_id: UserId, fic_id: FanficId, now: datetime) -> bool:
        key = (int(user_id), int(fic_id))
        if key in self._set:
            return False
        self._set.add(key)
        self._order.append((int(user_id), fic_id, now))
        return True

    async def remove(self, user_id: UserId, fic_id: FanficId) -> bool:
        key = (int(user_id), int(fic_id))
        if key not in self._set:
            return False
        self._set.discard(key)
        self._order = [x for x in self._order if (x[0], int(x[1])) != key]
        return True

    async def list_by_user(self, user_id: UserId, limit: int, offset: int) -> list[FanficId]:
        mine = [f for uid, f, _ in self._order if uid == int(user_id)]
        return mine[offset : offset + limit]


class FakeLikes(ILikesRepository):
    def __init__(self) -> None:
        self._set: set[tuple[int, int]] = set()

    async def exists(self, user_id: UserId, fic_id: FanficId) -> bool:
        return (int(user_id), int(fic_id)) in self._set

    async def add(self, user_id: UserId, fic_id: FanficId, now: datetime) -> bool:
        key = (int(user_id), int(fic_id))
        if key in self._set:
            return False
        self._set.add(key)
        return True

    async def remove(self, user_id: UserId, fic_id: FanficId) -> bool:
        key = (int(user_id), int(fic_id))
        if key not in self._set:
            return False
        self._set.discard(key)
        return True

    async def list_by_user(self, user_id: UserId, limit: int, offset: int) -> list[FanficId]:
        mine = [FanficId(fid) for uid, fid in self._set if uid == int(user_id)]
        return mine[offset : offset + limit]


class FakeReadsCompleted(IReadsCompletedRepository):
    def __init__(self) -> None:
        self._set: set[tuple[int, int]] = set()

    async def exists(self, user_id: UserId, chapter_id: ChapterId) -> bool:
        return (int(user_id), int(chapter_id)) in self._set

    async def upsert(self, user_id: UserId, chapter_id: ChapterId, now: datetime) -> bool:
        key = (int(user_id), int(chapter_id))
        if key in self._set:
            return False
        self._set.add(key)
        return True


class FakeReadingProgress(IReadingProgressRepository):
    def __init__(self) -> None:
        self._rows: dict[tuple[int, int], ReadingProgressDTO] = {}

    async def upsert(
        self,
        *,
        user_id: UserId,
        fic_id: FanficId,
        chapter_id: ChapterId,
        page_no: int,
        now: datetime,
    ) -> None:
        self._rows[(int(user_id), int(fic_id))] = ReadingProgressDTO(
            user_id=user_id,
            fic_id=fic_id,
            chapter_id=chapter_id,
            page_no=page_no,
            updated_at=now,
        )

    async def get(self, user_id: UserId, fic_id: FanficId) -> ReadingProgressDTO | None:
        return self._rows.get((int(user_id), int(fic_id)))

    async def list_recent(self, user_id: UserId, limit: int) -> list[ReadingProgressDTO]:
        mine = [v for (uid, _), v in self._rows.items() if uid == int(user_id)]
        mine.sort(key=lambda r: r.updated_at, reverse=True)
        return mine[:limit]


class FakeChapterPages(IChapterPagesRepository):
    def __init__(self) -> None:
        self._by_chapter: dict[int, list[Page]] = {}
        self.delete_calls: list[int] = []
        self.save_calls: list[tuple[int, int]] = []  # (chapter_id, pages_count)

    async def get(self, chapter_id: ChapterId, page_no: int) -> Page | None:
        pages = self._by_chapter.get(int(chapter_id), [])
        for p in pages:
            if p.page_no == page_no:
                return p
        return None

    async def count_by_chapter(self, chapter_id: ChapterId) -> int:
        return len(self._by_chapter.get(int(chapter_id), []))

    async def save_bulk(self, chapter_id: ChapterId, pages: list[Page]) -> None:
        key = int(chapter_id)
        existing = {p.page_no for p in self._by_chapter.get(key, [])}
        new = [p for p in pages if p.page_no not in existing]
        self._by_chapter.setdefault(key, []).extend(new)
        self.save_calls.append((key, len(new)))

    async def delete_by_chapter(self, chapter_id: ChapterId) -> None:
        self._by_chapter.pop(int(chapter_id), None)
        self.delete_calls.append(int(chapter_id))


class FakePageCache(IPageCache):
    def __init__(self) -> None:
        self._cache: dict[tuple[int, int], Page] = {}
        self.invalidate_calls: list[int] = []

    async def get(self, chapter_id: ChapterId, page_no: int) -> Page | None:
        return self._cache.get((int(chapter_id), page_no))

    async def set(self, chapter_id: ChapterId, page_no: int, page: Page) -> None:
        self._cache[(int(chapter_id), page_no)] = page

    async def invalidate_chapter(self, chapter_id: ChapterId) -> None:
        self._cache = {k: v for k, v in self._cache.items() if k[0] != int(chapter_id)}
        self.invalidate_calls.append(int(chapter_id))


class FakeProgressThrottle(IProgressThrottle):
    """Эмулируем SET NX EX 5 на ключе (user, fic, chapter).

    Смена главы создаёт новый ключ — throttle пропустит первую запись
    в новой главе даже если предыдущая была только что. Это отражает
    поведение реального RedisProgressThrottle (ключ включает chapter_id).
    """

    def __init__(self) -> None:
        self._blocked: set[tuple[int, int, int]] = set()

    def reset(self) -> None:
        self._blocked = set()

    async def try_acquire(self, user_id: UserId, fic_id: FanficId, chapter_id: ChapterId) -> bool:
        key = (int(user_id), int(fic_id), int(chapter_id))
        if key in self._blocked:
            return False
        self._blocked.add(key)
        return True


class FakeRepaginationQueue(IRepaginationQueue):
    def __init__(self) -> None:
        self.enqueued: list[int] = []

    async def enqueue(self, chapter_id: int) -> None:
        self.enqueued.append(chapter_id)


class FakeFanficFeed(IFanficFeedReader):
    def __init__(self) -> None:
        self.items: list[FeedItem] = []

    async def list_new(
        self, *, limit: int, offset: int, fandom_id: FandomId | None = None
    ) -> list[FeedItem]:
        matched = [it for it in self.items if fandom_id is None or it.fandom_id == fandom_id]
        return matched[offset : offset + limit]

    async def list_top(
        self, *, limit: int, offset: int, fandom_id: FandomId | None = None
    ) -> list[FeedItem]:
        matched = [it for it in self.items if fandom_id is None or it.fandom_id == fandom_id]
        matched.sort(key=lambda x: x.likes_count, reverse=True)
        return matched[offset : offset + limit]

    async def get_titles(self, fic_ids: list[FanficId]) -> dict[FanficId, str]:
        return {it.fic_id: it.title for it in self.items if it.fic_id in fic_ids}


# Расширяем FakeFanfics из _fakes.py счётчиками.
class FanficsWithCounters:
    """Mixin-класс: подключает атомарные счётчики к существующей FakeFanfics.

    Используй: `fanfics = extend_with_counters(FakeFanfics())`.
    """


def extend_with_counters(fake_fanfics: Any) -> Any:
    """Добавляет к FakeFanfics методы increment_likes/decrement_likes/.

    Мутирует переданный объект, возвращает его же.
    """

    likes_counts: dict[int, int] = {}
    reads_counts: dict[int, int] = {}

    async def increment_likes(fic_id: FanficId) -> None:
        likes_counts[int(fic_id)] = likes_counts.get(int(fic_id), 0) + 1

    async def decrement_likes(fic_id: FanficId) -> None:
        likes_counts[int(fic_id)] = max(0, likes_counts.get(int(fic_id), 0) - 1)

    async def increment_reads_completed(fic_id: FanficId) -> None:
        reads_counts[int(fic_id)] = reads_counts.get(int(fic_id), 0) + 1

    fake_fanfics.increment_likes = increment_likes  # type: ignore[attr-defined]
    fake_fanfics.decrement_likes = decrement_likes  # type: ignore[attr-defined]
    fake_fanfics.increment_reads_completed = (  # type: ignore[attr-defined]
        increment_reads_completed
    )
    fake_fanfics.likes_counts = likes_counts  # type: ignore[attr-defined]
    fake_fanfics.reads_counts = reads_counts  # type: ignore[attr-defined]
    return fake_fanfics
