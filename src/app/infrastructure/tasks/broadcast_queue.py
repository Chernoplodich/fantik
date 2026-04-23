"""Адаптер IBroadcastQueue → TaskIQ broadcast_broker."""

from __future__ import annotations

import asyncio

from app.application.broadcasts.ports import IBroadcastQueue
from app.domain.shared.types import BroadcastId, UserId


class TaskiqBroadcastQueue(IBroadcastQueue):
    async def enqueue_run(self, broadcast_id: BroadcastId) -> None:
        # Ленивый импорт: broadcast-задачи должны уже быть загружены (broadcast_main).
        from app.infrastructure.tasks.broadcast import run_broadcast

        await run_broadcast.kiq(int(broadcast_id))

    async def enqueue_deliver(
        self,
        *,
        broadcast_id: BroadcastId,
        user_id: UserId,
        delay_seconds: float = 0.0,
    ) -> None:
        from app.infrastructure.tasks.broadcast import deliver_one

        if delay_seconds > 0:
            # TaskIQ не предоставляет надёжный delay-механизм для ListQueueBroker
            # без middleware; на воркере нагрузка низкая, спим и перезаводим задачу.
            await asyncio.sleep(delay_seconds)
        await deliver_one.kiq(int(broadcast_id), int(user_id))

    async def enqueue_finalize(self, broadcast_id: BroadcastId) -> None:
        from app.infrastructure.tasks.broadcast import finalize_broadcast

        await finalize_broadcast.kiq(int(broadcast_id))
