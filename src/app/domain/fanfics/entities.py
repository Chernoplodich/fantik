"""Агрегаты Fanfic и Chapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domain.fanfics.events import (
    ChapterAdded,
    ChapterApproved,
    ChapterRejected,
    FanficApproved,
    FanficArchived,
    FanficEdited,
    FanficRejected,
    FanficSubmitted,
)
from app.domain.fanfics.exceptions import WrongStatusError
from app.domain.fanfics.value_objects import (
    AgeRatingCode,
    ChapterNumber,
    ChapterTitle,
    FanficTitle,
    FicStatus,
    Summary,
)
from app.domain.shared.events import EventEmitter
from app.domain.shared.types import (
    ChapterId,
    FandomId,
    FanficId,
    FanficVersionId,
    UserId,
)


EDITABLE_STATUSES: frozenset[FicStatus] = frozenset(
    {FicStatus.DRAFT, FicStatus.REJECTED, FicStatus.REVISING}
)

SUBMIT_FROM_STATUSES: frozenset[FicStatus] = frozenset(
    {FicStatus.DRAFT, FicStatus.REJECTED, FicStatus.REVISING, FicStatus.APPROVED}
)


@dataclass
class Chapter(EventEmitter):
    """Агрегат-глава. Живёт отдельно от Fanfic — модерится независимо."""

    id: ChapterId
    fic_id: FanficId
    number: ChapterNumber
    title: ChapterTitle
    text: str
    entities: list[dict[str, Any]] = field(default_factory=list)
    chars_count: int = 0  # UTF-16 units
    status: FicStatus = FicStatus.DRAFT
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        EventEmitter.__init__(self)

    @classmethod
    def create_draft(
        cls,
        *,
        fic_id: FanficId,
        number: ChapterNumber,
        title: ChapterTitle,
        text: str,
        entities: list[dict[str, Any]],
        chars_count: int,
        now: datetime,
    ) -> Chapter:
        # id=0: присваивается БД; mapper подставит реальный id.
        return cls(
            id=ChapterId(0),
            fic_id=fic_id,
            number=number,
            title=title,
            text=text,
            entities=list(entities),
            chars_count=chars_count,
            status=FicStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )

    def update_text(
        self,
        *,
        title: ChapterTitle,
        text: str,
        entities: list[dict[str, Any]],
        chars_count: int,
        now: datetime,
    ) -> None:
        if self.status not in (FicStatus.DRAFT, FicStatus.REJECTED, FicStatus.REVISING):
            raise WrongStatusError(
                "Редактировать главу можно только в статусах draft/rejected/revising."
            )
        self.title = title
        self.text = text
        self.entities = list(entities)
        self.chars_count = chars_count
        self.updated_at = now
        self.status = FicStatus.DRAFT  # после правки — снова draft

    def mark_pending(self, *, now: datetime) -> None:
        if self.status not in (FicStatus.DRAFT, FicStatus.REJECTED, FicStatus.REVISING):
            raise WrongStatusError("Главу можно отправить только из draft/rejected/revising.")
        self.status = FicStatus.PENDING
        self.updated_at = now

    def mark_draft(self, *, now: datetime) -> None:
        self.status = FicStatus.DRAFT
        self.updated_at = now

    def approve(self, *, now: datetime) -> None:
        if self.status != FicStatus.PENDING:
            raise WrongStatusError("Одобрить можно только pending-главу.")
        self.status = FicStatus.APPROVED
        self.updated_at = now
        self._emit(ChapterApproved(fic_id=self.fic_id, chapter_id=self.id))

    def reject(self, *, reason_ids: list[int], now: datetime) -> None:
        if self.status != FicStatus.PENDING:
            raise WrongStatusError("Отклонить можно только pending-главу.")
        self.status = FicStatus.REJECTED
        self.updated_at = now
        self._emit(
            ChapterRejected(
                fic_id=self.fic_id,
                chapter_id=self.id,
                reason_ids=tuple(reason_ids),
            )
        )


@dataclass
class Fanfic(EventEmitter):
    """Агрегат-фик. Инкапсулирует meta + lifecycle; не держит главы."""

    id: FanficId
    author_id: UserId
    title: FanficTitle
    summary: Summary
    summary_entities: list[dict[str, Any]]
    cover_file_id: str | None
    cover_file_unique_id: str | None
    fandom_id: FandomId
    age_rating_id: int
    status: FicStatus = FicStatus.DRAFT
    current_version_id: FanficVersionId | None = None
    chapters_count: int = 0
    chars_count: int = 0
    first_published_at: datetime | None = None
    last_edit_at: datetime | None = None
    archived_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        EventEmitter.__init__(self)

    # ---------- фабрика ----------

    @classmethod
    def create_draft(
        cls,
        *,
        author_id: UserId,
        title: FanficTitle,
        summary: Summary,
        summary_entities: list[dict[str, Any]],
        fandom_id: FandomId,
        age_rating_id: int,
        cover_file_id: str | None,
        cover_file_unique_id: str | None,
        now: datetime,
    ) -> Fanfic:
        return cls(
            id=FanficId(0),
            author_id=author_id,
            title=title,
            summary=summary,
            summary_entities=list(summary_entities),
            cover_file_id=cover_file_id,
            cover_file_unique_id=cover_file_unique_id,
            fandom_id=fandom_id,
            age_rating_id=age_rating_id,
            status=FicStatus.DRAFT,
            created_at=now,
            updated_at=now,
        )

    # ---------- meta ----------

    def update_meta(
        self,
        *,
        title: FanficTitle,
        summary: Summary,
        summary_entities: list[dict[str, Any]],
        fandom_id: FandomId,
        age_rating_id: int,
        cover_file_id: str | None,
        cover_file_unique_id: str | None,
        now: datetime,
    ) -> None:
        if self.status not in EDITABLE_STATUSES:
            raise WrongStatusError(
                "Редактировать можно только в статусах draft/rejected/revising. "
                "Для approved отправь на повторную модерацию."
            )
        self.title = title
        self.summary = summary
        self.summary_entities = list(summary_entities)
        self.fandom_id = fandom_id
        self.age_rating_id = age_rating_id
        self.cover_file_id = cover_file_id
        self.cover_file_unique_id = cover_file_unique_id
        self.updated_at = now
        self._emit(FanficEdited(fic_id=self.id, author_id=self.author_id))

    # ---------- счётчики ----------

    def bump_chapters(self, *, chars_delta: int) -> None:
        self.chapters_count += 1
        self.chars_count += chars_delta

    def drop_chapter(self, *, chars_delta: int) -> None:
        self.chapters_count = max(0, self.chapters_count - 1)
        self.chars_count = max(0, self.chars_count - chars_delta)

    def replace_chars_delta(self, *, old: int, new: int) -> None:
        self.chars_count = max(0, self.chars_count - old + new)

    # ---------- lifecycle ----------

    def submit_for_review(self, *, now: datetime) -> None:
        if self.status not in SUBMIT_FROM_STATUSES:
            raise WrongStatusError(
                "Отправить на модерацию можно из draft/rejected/revising/approved."
            )
        self.status = FicStatus.PENDING
        self.updated_at = now
        self.last_edit_at = now
        self._emit(FanficSubmitted(fic_id=self.id, author_id=self.author_id))

    def cancel_submission(self, *, now: datetime) -> None:
        if self.status != FicStatus.PENDING:
            raise WrongStatusError("Отменить можно только pending-фик.")
        self.status = FicStatus.DRAFT
        self.updated_at = now

    def approve(
        self,
        *,
        version_id: FanficVersionId,
        now: datetime,
    ) -> None:
        if self.status != FicStatus.PENDING:
            raise WrongStatusError("Одобрить можно только pending-фик.")
        first = self.first_published_at is None
        self.status = FicStatus.APPROVED
        if first:
            self.first_published_at = now
        self.current_version_id = version_id
        self.updated_at = now
        self._emit(FanficApproved(fic_id=self.id, author_id=self.author_id, first_publish=first))

    def reject(self, *, reason_ids: list[int], now: datetime) -> None:
        if self.status != FicStatus.PENDING:
            raise WrongStatusError("Отклонить можно только pending-фик.")
        self.status = FicStatus.REJECTED
        self.updated_at = now
        self._emit(
            FanficRejected(
                fic_id=self.id,
                author_id=self.author_id,
                reason_ids=tuple(reason_ids),
            )
        )

    def mark_revising(self, *, now: datetime) -> None:
        """Открыть режим правки.

        Разрешено из:
        - REJECTED  → автор «Доработать» после отказа.
        - APPROVED  → автор «Внести правку» в опубликованную работу; до новой
          модерации фик временно выпадает из каталога.
        """
        if self.status not in (FicStatus.REJECTED, FicStatus.APPROVED):
            raise WrongStatusError(
                "Начать правку можно только из опубликованной или отклонённой работы."
            )
        self.status = FicStatus.REVISING
        self.updated_at = now

    def archive(self, *, now: datetime) -> None:
        self.status = FicStatus.ARCHIVED
        self.archived_at = now
        self.updated_at = now
        self._emit(FanficArchived(fic_id=self.id, author_id=self.author_id))

    def announce_chapter_added(self, *, chapter_id: ChapterId, number: int) -> None:
        """Хелпер для use case add_chapter — эмитит ChapterAdded из агрегата Fanfic."""
        self._emit(ChapterAdded(fic_id=self.id, chapter_id=chapter_id, number=number))
