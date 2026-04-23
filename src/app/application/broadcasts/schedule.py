"""Use case: отложить рассылку на `scheduled_at` (draft/scheduled → scheduled)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.application.broadcasts.ports import IBroadcastRepository
from app.application.fanfics.ports import IOutboxRepository
from app.application.moderation.ports import IAuditLog
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.errors import NotFoundError, ValidationError
from app.domain.broadcasts.segment import interpret_segment
from app.domain.shared.types import BroadcastId, UserId


@dataclass(frozen=True, kw_only=True)
class ScheduleBroadcastCommand:
    broadcast_id: int
    actor_id: int
    scheduled_at: datetime


class ScheduleBroadcastUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        broadcasts: IBroadcastRepository,
        outbox: IOutboxRepository,
        audit: IAuditLog,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._broadcasts = broadcasts
        self._outbox = outbox
        self._audit = audit
        self._clock = clock

    async def __call__(self, cmd: ScheduleBroadcastCommand) -> None:
        now = self._clock.now()
        # Минимальный зазор от now — даём scheduler-tick'у успеть подхватить.
        if cmd.scheduled_at <= now - timedelta(seconds=5):
            raise ValidationError("Нельзя запланировать рассылку в прошлое.")

        async with self._uow:
            bc = await self._broadcasts.get(BroadcastId(int(cmd.broadcast_id)))
            if bc is None:
                raise NotFoundError("Рассылка не найдена.")
            # Валидируем сегмент — без него рассылку не запускаем.
            interpret_segment(bc.segment_spec)

            bc.schedule(scheduled_at=cmd.scheduled_at)
            await self._broadcasts.save(bc)

            payload: dict[str, Any] = {
                "broadcast_id": int(bc.id),
                "scheduled_at": cmd.scheduled_at.isoformat(),
            }
            await self._outbox.append(
                event_type="broadcast.scheduled",
                payload=payload,
                now=now,
            )
            await self._audit.log(
                actor_id=UserId(int(cmd.actor_id)),
                action="broadcast.schedule",
                target_type="broadcast",
                target_id=int(bc.id),
                payload=payload,
                now=now,
            )
            await self._uow.commit()
