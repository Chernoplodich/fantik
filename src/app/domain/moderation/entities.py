"""Агрегат ModerationCase."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.domain.fanfics.value_objects import MqDecision, MqKind
from app.domain.moderation.events import (
    ModerationCaseApproved,
    ModerationCaseCancelled,
    ModerationCaseLocked,
    ModerationCaseRejected,
    ModerationCaseUnlocked,
)
from app.domain.moderation.exceptions import (
    CannotModerateOwnWorkError,
    CaseAlreadyDecidedError,
    CaseAlreadyLockedError,
    CaseNotLockedByThisModeratorError,
    ReasonsRequiredForRejectError,
)
from app.domain.moderation.value_objects import LOCK_DURATION
from app.domain.shared.events import EventEmitter
from app.domain.shared.types import (
    ChapterId,
    FanficId,
    ModerationCaseId,
    UserId,
)


@dataclass
class ModerationCase(EventEmitter):
    id: ModerationCaseId
    fic_id: FanficId
    chapter_id: ChapterId | None
    kind: MqKind
    submitted_by: UserId
    submitted_at: datetime
    locked_by: UserId | None = None
    locked_until: datetime | None = None
    decision: MqDecision | None = None
    decision_reason_ids: list[int] = field(default_factory=list)
    decision_comment: str | None = None
    decision_comment_entities: list[dict[str, Any]] = field(default_factory=list)
    decided_by: UserId | None = None
    decided_at: datetime | None = None
    cancelled_at: datetime | None = None

    def __post_init__(self) -> None:
        EventEmitter.__init__(self)

    # ---------- helpers ----------

    def raise_if_owned_by(self, user_id: UserId) -> None:
        if self.submitted_by == user_id:
            raise CannotModerateOwnWorkError(
                "Модератор не может модерировать свои работы."
            )

    def is_locked(self, *, now: datetime) -> bool:
        return (
            self.locked_by is not None
            and self.locked_until is not None
            and self.locked_until > now
        )

    def _require_open(self) -> None:
        if self.decision is not None:
            raise CaseAlreadyDecidedError("Решение уже принято.")
        if self.cancelled_at is not None:
            raise CaseAlreadyDecidedError("Задание отменено автором.")

    def _require_lock_of(self, moderator_id: UserId, *, now: datetime) -> None:
        if self.locked_by is None or not self.is_locked(now=now):
            raise CaseNotLockedByThisModeratorError("Lock истёк или не установлен.")
        if self.locked_by != moderator_id:
            raise CaseNotLockedByThisModeratorError("Задание залочено другим модератором.")

    # ---------- lifecycle ----------

    def lock(self, *, moderator_id: UserId, now: datetime) -> None:
        self._require_open()
        self.raise_if_owned_by(moderator_id)
        if self.is_locked(now=now) and self.locked_by != moderator_id:
            raise CaseAlreadyLockedError("Задание уже залочено.")
        self.locked_by = moderator_id
        self.locked_until = now + LOCK_DURATION
        self._emit(ModerationCaseLocked(case_id=self.id, moderator_id=moderator_id))

    def unlock(self, *, moderator_id: UserId, now: datetime) -> None:
        self._require_open()
        self._require_lock_of(moderator_id, now=now)
        self.locked_by = None
        self.locked_until = None
        self._emit(ModerationCaseUnlocked(case_id=self.id, moderator_id=moderator_id))

    def approve(
        self,
        *,
        moderator_id: UserId,
        comment: str | None,
        entities: list[dict[str, Any]],
        now: datetime,
    ) -> None:
        self._require_open()
        self._require_lock_of(moderator_id, now=now)
        self.decision = MqDecision.APPROVED
        self.decision_reason_ids = []
        self.decision_comment = comment
        self.decision_comment_entities = list(entities)
        self.decided_by = moderator_id
        self.decided_at = now
        self.locked_by = None
        self.locked_until = None
        self._emit(ModerationCaseApproved(case_id=self.id, moderator_id=moderator_id))

    def reject(
        self,
        *,
        moderator_id: UserId,
        reason_ids: list[int],
        comment: str | None,
        entities: list[dict[str, Any]],
        now: datetime,
    ) -> None:
        self._require_open()
        self._require_lock_of(moderator_id, now=now)
        if not reason_ids:
            raise ReasonsRequiredForRejectError(
                "Выбери хотя бы одну причину отказа."
            )
        self.decision = MqDecision.REJECTED
        self.decision_reason_ids = list(reason_ids)
        self.decision_comment = comment
        self.decision_comment_entities = list(entities)
        self.decided_by = moderator_id
        self.decided_at = now
        self.locked_by = None
        self.locked_until = None
        self._emit(
            ModerationCaseRejected(
                case_id=self.id,
                moderator_id=moderator_id,
                reason_ids=tuple(reason_ids),
            )
        )

    def cancel(self, *, now: datetime) -> None:
        self._require_open()
        self.cancelled_at = now
        self.locked_by = None
        self.locked_until = None
        self._emit(ModerationCaseCancelled(case_id=self.id))
