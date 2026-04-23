"""Use case: немедленно запустить рассылку (draft/scheduled → running)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.broadcasts.ports import IBroadcastQueue, IBroadcastRepository
from app.application.fanfics.ports import IOutboxRepository
from app.application.moderation.ports import IAuditLog
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.domain.broadcasts.segment import interpret_segment
from app.domain.shared.types import BroadcastId, UserId


@dataclass(frozen=True, kw_only=True)
class LaunchBroadcastCommand:
    broadcast_id: int
    actor_id: int


class LaunchBroadcastUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        broadcasts: IBroadcastRepository,
        outbox: IOutboxRepository,
        audit: IAuditLog,
        queue: IBroadcastQueue,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._broadcasts = broadcasts
        self._outbox = outbox
        self._audit = audit
        self._queue = queue
        self._clock = clock

    async def __call__(self, cmd: LaunchBroadcastCommand) -> None:
        async with self._uow:
            bc = await self._broadcasts.get(BroadcastId(int(cmd.broadcast_id)))
            if bc is None:
                raise NotFoundError("Рассылка не найдена.")
            interpret_segment(bc.segment_spec)

            now = self._clock.now()
            bc.launch(now=now)
            await self._broadcasts.save(bc)

            payload: dict[str, Any] = {"broadcast_id": int(bc.id)}
            await self._outbox.append(
                event_type="broadcast.launched",
                payload=payload,
                now=now,
            )
            await self._audit.log(
                actor_id=UserId(int(cmd.actor_id)),
                action="broadcast.launch",
                target_type="broadcast",
                target_id=int(bc.id),
                payload=payload,
                now=now,
            )
            await self._uow.commit()

        # Enqueue ПОСЛЕ commit: если enqueue упадёт, у нас status=running и
        # scheduler/finalize всё равно подберёт (через finalize_running_broadcasts).
        await self._queue.enqueue_run(BroadcastId(int(bc.id)))
