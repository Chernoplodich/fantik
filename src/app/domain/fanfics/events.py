"""Доменные события фиков/глав."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from app.domain.shared.events import DomainEvent
from app.domain.shared.types import (
    ChapterId,
    FanficId,
    ModerationCaseId,
    TagId,
    UserId,
)


@dataclass(frozen=True, kw_only=True)
class FanficSubmitted(DomainEvent):
    fic_id: FanficId
    author_id: UserId
    case_id: ModerationCaseId | None = None
    name: ClassVar[str] = "fanfic.submitted"


@dataclass(frozen=True, kw_only=True)
class FanficApproved(DomainEvent):
    fic_id: FanficId
    author_id: UserId
    first_publish: bool
    name: ClassVar[str] = "fanfic.approved"


@dataclass(frozen=True, kw_only=True)
class FanficRejected(DomainEvent):
    fic_id: FanficId
    author_id: UserId
    reason_ids: tuple[int, ...]
    name: ClassVar[str] = "fanfic.rejected"


@dataclass(frozen=True, kw_only=True)
class FanficEdited(DomainEvent):
    fic_id: FanficId
    author_id: UserId
    name: ClassVar[str] = "fanfic.edited"


@dataclass(frozen=True, kw_only=True)
class FanficArchived(DomainEvent):
    fic_id: FanficId
    author_id: UserId
    name: ClassVar[str] = "fanfic.archived"


@dataclass(frozen=True, kw_only=True)
class ChapterAdded(DomainEvent):
    fic_id: FanficId
    chapter_id: ChapterId
    number: int
    name: ClassVar[str] = "chapter.added"


@dataclass(frozen=True, kw_only=True)
class ChapterApproved(DomainEvent):
    fic_id: FanficId
    chapter_id: ChapterId
    name: ClassVar[str] = "chapter.approved"


@dataclass(frozen=True, kw_only=True)
class ChapterRejected(DomainEvent):
    fic_id: FanficId
    chapter_id: ChapterId
    reason_ids: tuple[int, ...]
    name: ClassVar[str] = "chapter.rejected"


@dataclass(frozen=True, kw_only=True)
class TagEnsured(DomainEvent):
    tag_id: TagId
    slug: str
    created: bool
    name: ClassVar[str] = "tag.ensured"
