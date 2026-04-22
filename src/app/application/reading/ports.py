"""Порты application-слоя для чтения."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.fanfics.services.paginator import Page
from app.domain.shared.types import ChapterId, FandomId, FanficId, UserId


# ---------- DTO ----------


@dataclass(frozen=True, kw_only=True)
class ReadingProgressDTO:
    user_id: UserId
    fic_id: FanficId
    chapter_id: ChapterId
    page_no: int
    updated_at: datetime


@dataclass(frozen=True, kw_only=True)
class FeedItem:
    fic_id: FanficId
    title: str
    author_id: UserId
    author_nick: str | None
    fandom_id: FandomId
    fandom_name: str | None
    chapters_count: int
    likes_count: int
    reads_completed_count: int
    first_published_at: datetime | None


@dataclass(frozen=True, kw_only=True)
class ShelfItem:
    fic_id: FanficId
    title: str
    chapter_id: ChapterId | None  # None для bookmark/like
    chapter_number: int | None
    page_no: int | None
    updated_at: datetime | None


# ---------- Repositories ----------


class IChapterPagesRepository(Protocol):
    async def get(self, chapter_id: ChapterId, page_no: int) -> Page | None: ...

    async def count_by_chapter(self, chapter_id: ChapterId) -> int: ...

    async def save_bulk(self, chapter_id: ChapterId, pages: list[Page]) -> None:
        """Идемпотентная вставка: ON CONFLICT (chapter_id, page_no) DO NOTHING."""
        ...

    async def delete_by_chapter(self, chapter_id: ChapterId) -> None: ...


class IBookmarksRepository(Protocol):
    async def exists(self, user_id: UserId, fic_id: FanficId) -> bool: ...

    async def add(self, user_id: UserId, fic_id: FanficId, now: datetime) -> bool:
        """True — добавили (INSERT), False — уже была."""
        ...

    async def remove(self, user_id: UserId, fic_id: FanficId) -> bool:
        """True — удалили, False — не было."""
        ...

    async def list_by_user(self, user_id: UserId, limit: int, offset: int) -> list[FanficId]: ...


class ILikesRepository(Protocol):
    async def exists(self, user_id: UserId, fic_id: FanficId) -> bool: ...

    async def add(self, user_id: UserId, fic_id: FanficId, now: datetime) -> bool: ...

    async def remove(self, user_id: UserId, fic_id: FanficId) -> bool: ...

    async def list_by_user(self, user_id: UserId, limit: int, offset: int) -> list[FanficId]: ...


class IReadsCompletedRepository(Protocol):
    async def exists(self, user_id: UserId, chapter_id: ChapterId) -> bool: ...

    async def upsert(self, user_id: UserId, chapter_id: ChapterId, now: datetime) -> bool:
        """True — inserted (first time), False — уже было."""
        ...


class IReadingProgressRepository(Protocol):
    async def upsert(
        self,
        *,
        user_id: UserId,
        fic_id: FanficId,
        chapter_id: ChapterId,
        page_no: int,
        now: datetime,
    ) -> None: ...

    async def get(self, user_id: UserId, fic_id: FanficId) -> ReadingProgressDTO | None: ...

    async def list_recent(self, user_id: UserId, limit: int) -> list[ReadingProgressDTO]: ...


class IFanficFeedReader(Protocol):
    """Read-only витрина каталога. Работает по partial-индексам."""

    async def list_new(
        self, *, limit: int, offset: int, fandom_id: FandomId | None = None
    ) -> list[FeedItem]: ...

    async def list_top(
        self, *, limit: int, offset: int, fandom_id: FandomId | None = None
    ) -> list[FeedItem]: ...

    async def get_titles(self, fic_ids: list[FanficId]) -> dict[FanficId, str]: ...


# ---------- Redis ports ----------


class IPageCache(Protocol):
    async def get(self, chapter_id: ChapterId, page_no: int) -> Page | None: ...

    async def set(self, chapter_id: ChapterId, page_no: int, page: Page) -> None: ...

    async def invalidate_chapter(self, chapter_id: ChapterId) -> None: ...


class IProgressThrottle(Protocol):
    async def try_acquire(self, user_id: UserId, fic_id: FanficId, chapter_id: ChapterId) -> bool:
        """SET NX EX 5 на ключе (user_id, fic_id, chapter_id).

        Смена главы создаёт НОВЫЙ ключ → первая запись в новой главе
        проходит сразу. Это гарантирует, что `reading_progress.chapter_id`
        всегда актуальный (критично для кнопки «▶ Продолжить»).
        """
        ...


class IRepaginationQueue(Protocol):
    async def enqueue(self, chapter_id: int) -> None: ...
