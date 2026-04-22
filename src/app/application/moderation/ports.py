"""Порты application-слоя для модерации."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.domain.fanfics.value_objects import MqKind
from app.domain.moderation.entities import ModerationCase
from app.domain.moderation.value_objects import RejectionReason
from app.domain.shared.types import (
    AuditLogId,
    ChapterId,
    FanficId,
    ModerationCaseId,
    ModerationReasonId,
    UserId,
)


@dataclass(frozen=True, kw_only=True)
class ActiveCaseLock:
    """Информация о текущем lock'е по fic_id (для cancel_submission)."""

    case_id: ModerationCaseId
    locked_by: UserId | None
    locked_until: datetime | None


class IModerationRepository(Protocol):
    async def create_case(
        self,
        *,
        fic_id: FanficId,
        chapter_id: ChapterId | None,
        kind: MqKind,
        submitted_by: UserId,
        now: datetime,
    ) -> ModerationCase: ...

    async def get_by_id(self, case_id: ModerationCaseId) -> ModerationCase | None: ...

    async def get_open_by_fic(self, fic_id: FanficId) -> ModerationCase | None:
        """Вернуть незакрытый case для фика (decision IS NULL AND cancelled_at IS NULL)."""
        ...

    async def pick_next(
        self, *, moderator_id: UserId, now: datetime
    ) -> ModerationCase | None:
        """Атомарно залочить следующую задачу через CTE + SKIP LOCKED + UPDATE RETURNING.

        WHERE decision IS NULL AND cancelled_at IS NULL
          AND (locked_until IS NULL OR locked_until < :now)
          AND submitted_by != :moderator_id
        """
        ...

    async def save_decision_idempotent(self, case: ModerationCase) -> bool:
        """UPDATE ... WHERE decision IS NULL.

        Возвращает True, если строка обновилась; False, если другой модератор уже решил.
        """
        ...

    async def unlock(
        self, *, case_id: ModerationCaseId, moderator_id: UserId
    ) -> bool: ...

    async def release_stale_locks(self, *, now: datetime) -> int:
        """Вернуть число снятых lock'ов (locked_until < now)."""
        ...

    async def mark_cancelled(
        self, *, case_id: ModerationCaseId, now: datetime
    ) -> bool: ...


class IReasonRepository(Protocol):
    async def list_active(self) -> list[RejectionReason]: ...

    async def get_by_ids(
        self, reason_ids: list[ModerationReasonId]
    ) -> list[RejectionReason]: ...


class IModeratorNotifier(Protocol):
    async def notify_new_case(
        self,
        *,
        case_id: ModerationCaseId,
        kind: str,
        fic_id: FanficId,
        fic_title: str,
        author_id: UserId,
    ) -> None: ...


class IAuditLog(Protocol):
    async def log(
        self,
        *,
        actor_id: UserId | None,
        action: str,
        target_type: str,
        target_id: int,
        payload: dict[str, Any],
        now: datetime,
    ) -> AuditLogId: ...
