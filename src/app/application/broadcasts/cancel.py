"""Use case: отменить рассылку (scheduled/running → cancelled).

Для running-рассылок deliver_one сам увидит статус=cancelled и сделает no-op
(уже отправленных не отзываем — TG не даёт).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.broadcasts.ports import IBroadcastRepository
from app.application.fanfics.ports import IOutboxRepository
from app.application.moderation.ports import IAuditLog
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.domain.shared.types import BroadcastId, UserId


@dataclass(frozen=True, kw_only=True)
class CancelBroadcastCommand:
    broadcast_id: int
    actor_id: int


class CancelBroadcastUseCase:
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

    async def __call__(self, cmd: CancelBroadcastCommand) -> None:
        async with self._uow:
            bc = await self._broadcasts.get(BroadcastId(int(cmd.broadcast_id)))
            if bc is None:
                raise NotFoundError("Рассылка не найдена.")
            if bc.is_terminal:
                # Идемпотентность: повторный cancel на finished/cancelled/failed — no-op.
                await self._uow.commit()
                return

            now = self._clock.now()
            bc.cancel(actor_id=UserId(int(cmd.actor_id)), now=now)
            await self._broadcasts.save(bc)

            payload = {"broadcast_id": int(bc.id)}
            await self._outbox.append(
                event_type="broadcast.cancelled",
                payload=payload,
                now=now,
            )
            await self._audit.log(
                actor_id=UserId(int(cmd.actor_id)),
                action="broadcast.cancel",
                target_type="broadcast",
                target_id=int(bc.id),
                payload=payload,
                now=now,
            )
            await self._uow.commit()
