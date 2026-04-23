"""Порты application-слоя для фиков."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.domain.fanfics.entities import Chapter, Fanfic
from app.domain.fanfics.value_objects import (
    AgeRatingCode,
    FicStatus,
    TagName,
    TagSlug,
)
from app.domain.moderation.value_objects import RejectionReason
from app.domain.shared.types import (
    ChapterId,
    FandomId,
    FanficId,
    FanficVersionId,
    OutboxId,
    TagId,
    UserId,
)


# ---------- DTO / read-models ----------


@dataclass(frozen=True, kw_only=True)
class FandomRef:
    id: FandomId
    slug: str
    name: str
    category: str


@dataclass(frozen=True, kw_only=True)
class AgeRatingRef:
    id: int
    code: AgeRatingCode
    name: str
    description: str
    min_age: int | None
    sort_order: int


@dataclass(frozen=True, kw_only=True)
class TagRef:
    id: TagId
    name: TagName
    slug: TagSlug
    kind: str
    approved: bool


@dataclass(frozen=True, kw_only=True)
class FanficListItem:
    fic_id: FanficId
    title: str
    status: FicStatus
    chapters_count: int
    updated_at: datetime | None


@dataclass(frozen=True, kw_only=True)
class FanficWithChapters:
    fic: Fanfic
    chapters: list[Chapter]
    tags: list[TagRef]


# ---------- Repositories ----------


class IFanficRepository(Protocol):
    async def get(self, fic_id: FanficId) -> Fanfic | None: ...

    async def get_with_chapters(self, fic_id: FanficId) -> FanficWithChapters | None: ...

    async def save(self, fic: Fanfic) -> Fanfic:
        """Сохранить (INSERT если id==0, UPDATE иначе). Возвращает с заполненным id."""
        ...

    async def list_by_author_paginated(
        self, *, author_id: UserId, limit: int, offset: int
    ) -> tuple[list[FanficListItem], int]:
        """Список + total count."""
        ...

    async def count_submitted_today(self, *, author_id: UserId, tz: str) -> int: ...

    async def increment_likes(self, fic_id: FanficId) -> None:
        """Атомарный UPDATE fanfics SET likes_count = likes_count + 1."""
        ...

    async def decrement_likes(self, fic_id: FanficId) -> None:
        """Атомарный UPDATE fanfics SET likes_count = GREATEST(likes_count - 1, 0)."""
        ...

    async def increment_reads_completed(self, fic_id: FanficId) -> None:
        """Атомарный UPDATE fanfics SET reads_completed_count = reads_completed_count + 1."""
        ...


class IChapterRepository(Protocol):
    async def get(self, chapter_id: ChapterId) -> Chapter | None: ...

    async def save(self, chapter: Chapter) -> Chapter: ...

    async def list_by_fic(self, fic_id: FanficId) -> list[Chapter]: ...

    async def list_by_fic_and_statuses(
        self, fic_id: FanficId, statuses: list[FicStatus]
    ) -> list[Chapter]: ...

    async def delete(self, chapter_id: ChapterId) -> None: ...

    async def count_by_fic(self, fic_id: FanficId) -> int: ...

    async def next_number(self, fic_id: FanficId) -> int: ...


class ITagRepository(Protocol):
    async def ensure(self, *, name: TagName, slug: TagSlug, kind: str) -> tuple[TagRef, bool]:
        """Idempotent upsert. Возвращает (ref, created)."""
        ...

    async def list_by_fic_ids(self, fic_ids: list[FanficId]) -> dict[FanficId, list[TagRef]]: ...

    async def list_by_fic(self, fic_id: FanficId) -> list[TagRef]: ...

    async def replace_for_fic(self, *, fic_id: FanficId, tag_ids: list[TagId]) -> None: ...


class IFanficVersionRepository(Protocol):
    async def next_version_no(self, fic_id: FanficId) -> int: ...

    async def get_latest_id(self, fic_id: FanficId) -> FanficVersionId | None: ...

    async def create_snapshot(
        self,
        *,
        fic_id: FanficId,
        version_no: int,
        title: str,
        summary: str,
        summary_entities: list[dict[str, Any]],
        snapshot_chapters: list[dict[str, Any]],
        now: datetime,
    ) -> FanficVersionId: ...


class IOutboxRepository(Protocol):
    async def append(
        self, *, event_type: str, payload: dict[str, Any], now: datetime
    ) -> OutboxId: ...


class IReferenceReader(Protocol):
    async def list_fandoms_paginated(
        self, *, limit: int, offset: int, active_only: bool = True
    ) -> tuple[list[FandomRef], int]: ...

    async def get_fandom(self, fandom_id: FandomId) -> FandomRef | None: ...

    async def list_age_ratings(self) -> list[AgeRatingRef]: ...

    async def get_age_rating(self, rating_id: int) -> AgeRatingRef | None: ...


class IAuthorNotifier(Protocol):
    async def notify_approved(
        self, *, author_id: UserId, fic_id: FanficId, fic_title: str
    ) -> None: ...

    async def notify_rejected(
        self,
        *,
        author_id: UserId,
        fic_id: FanficId,
        fic_title: str,
        reasons: list[RejectionReason],
        comment: str | None,
        comment_entities: list[dict[str, Any]],
    ) -> None: ...

    async def notify_chapter_approved(
        self,
        *,
        author_id: UserId,
        fic_id: FanficId,
        chapter_id: ChapterId,
        chapter_number: int,
        fic_title: str,
    ) -> None: ...

    async def notify_chapter_rejected(
        self,
        *,
        author_id: UserId,
        fic_id: FanficId,
        chapter_id: ChapterId,
        chapter_number: int,
        fic_title: str,
        reasons: list[RejectionReason],
        comment: str | None,
        comment_entities: list[dict[str, Any]],
    ) -> None: ...
