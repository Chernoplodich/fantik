"""Use case: запись произвольного трекинг-события."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.application.shared.ports import UnitOfWork
from app.application.tracking.ports import ITrackingRepository
from app.application.users.ports import IUserRepository
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.domain.shared.types import UserId
from app.domain.tracking.entities import TrackingEvent
from app.domain.tracking.value_objects import TrackingEventType


@dataclass(frozen=True, kw_only=True)
class RecordEventCommand:
    user_id: int
    event_type: TrackingEventType
    payload: dict[str, Any] = field(default_factory=dict)
    only_once: bool = False


class RecordEventUseCase:
    """Для first_read/first_publish — пропускать, если событие уже было (only_once=True).

    Источник кампании (utm_source_code_id) читается из users.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        tracking: ITrackingRepository,
        users: IUserRepository,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._tracking = tracking
        self._users = users
        self._clock = clock

    async def __call__(self, cmd: RecordEventCommand) -> bool:
        """Возвращает True, если событие было записано."""
        uid = UserId(cmd.user_id)
        async with self._uow:
            if cmd.only_once and await self._tracking.has_event_for_user(
                uid, cmd.event_type.value
            ):
                return False
            user = await self._users.get(uid)
            if user is None:
                raise NotFoundError("Пользователь не найден.")
            await self._tracking.record(
                TrackingEvent(
                    id=None,
                    code_id=user.utm_source_code_id,
                    user_id=uid,
                    event_type=cmd.event_type,
                    payload=cmd.payload,
                    created_at=self._clock.now(),
                )
            )
            await self._uow.commit()
        return True
