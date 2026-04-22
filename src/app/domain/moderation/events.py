"""Доменные события модерации."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from app.domain.shared.events import DomainEvent
from app.domain.shared.types import (
    ChapterId,
    FanficId,
    ModerationCaseId,
    UserId,
)


@dataclass(frozen=True, kw_only=True)
class ModerationCaseCreated(DomainEvent):
    case_id: ModerationCaseId
    fic_id: FanficId
    chapter_id: ChapterId | None
    kind: str
    submitted_by: UserId
    name: ClassVar[str] = "moderation.case_created"


@dataclass(frozen=True, kw_only=True)
class ModerationCaseLocked(DomainEvent):
    case_id: ModerationCaseId
    moderator_id: UserId
    name: ClassVar[str] = "moderation.case_locked"


@dataclass(frozen=True, kw_only=True)
class ModerationCaseUnlocked(DomainEvent):
    case_id: ModerationCaseId
    moderator_id: UserId
    name: ClassVar[str] = "moderation.case_unlocked"


@dataclass(frozen=True, kw_only=True)
class ModerationCaseApproved(DomainEvent):
    case_id: ModerationCaseId
    moderator_id: UserId
    name: ClassVar[str] = "moderation.case_approved"


@dataclass(frozen=True, kw_only=True)
class ModerationCaseRejected(DomainEvent):
    case_id: ModerationCaseId
    moderator_id: UserId
    reason_ids: tuple[int, ...]
    name: ClassVar[str] = "moderation.case_rejected"


@dataclass(frozen=True, kw_only=True)
class ModerationCaseCancelled(DomainEvent):
    case_id: ModerationCaseId
    name: ClassVar[str] = "moderation.case_cancelled"
