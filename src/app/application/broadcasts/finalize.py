"""Use case: финализация running-рассылки.

Вызывается периодически (scheduler tick каждую минуту). Для running-рассылок
считает `count_by_status`; если pending=0 — переводит в finished,
обновляет stats, пишет audit и отправляет admin'у сводку.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.broadcasts.ports import (
    IBroadcastBot,
    IBroadcastRepository,
    IDeliveryRepository,
)
from app.application.fanfics.ports import IOutboxRepository
from app.application.moderation.ports import IAuditLog
from app.application.shared.ports import UnitOfWork
from app.core.clock import Clock
from app.core.logging import get_logger
from app.domain.broadcasts.value_objects import BroadcastStatus, DeliveryStatus
from app.domain.shared.types import BroadcastId

log = get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class FinalizeBroadcastCommand:
    broadcast_id: int


@dataclass(frozen=True, kw_only=True)
class FinalizeBroadcastResult:
    finalized: bool
    stats: dict[str, int]


class FinalizeBroadcastUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        broadcasts: IBroadcastRepository,
        deliveries: IDeliveryRepository,
        outbox: IOutboxRepository,
        audit: IAuditLog,
        bot: IBroadcastBot,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._broadcasts = broadcasts
        self._deliveries = deliveries
        self._outbox = outbox
        self._audit = audit
        self._bot = bot
        self._clock = clock

    async def __call__(self, cmd: FinalizeBroadcastCommand) -> FinalizeBroadcastResult:
        broadcast_id = BroadcastId(int(cmd.broadcast_id))
        async with self._uow:
            bc = await self._broadcasts.get(broadcast_id)
            if bc is None or bc.status != BroadcastStatus.RUNNING:
                await self._uow.commit()
                return FinalizeBroadcastResult(finalized=False, stats={})

            counts = await self._deliveries.count_by_status(broadcast_id)
            pending = int(counts.get(DeliveryStatus.PENDING, 0))
            if pending > 0:
                await self._uow.commit()
                return FinalizeBroadcastResult(
                    finalized=False,
                    stats={
                        "pending": pending,
                        "sent": int(counts.get(DeliveryStatus.SENT, 0)),
                        "failed": int(counts.get(DeliveryStatus.FAILED, 0)),
                        "blocked": int(counts.get(DeliveryStatus.BLOCKED, 0)),
                    },
                )

            sent = int(counts.get(DeliveryStatus.SENT, 0))
            failed = int(counts.get(DeliveryStatus.FAILED, 0))
            blocked = int(counts.get(DeliveryStatus.BLOCKED, 0))
            total = sent + failed + blocked
            stats = {
                "total": total,
                "sent": sent,
                "failed": failed,
                "blocked": blocked,
            }

            now = self._clock.now()
            bc.mark_finished(stats=stats, now=now)
            await self._broadcasts.save(bc)

            payload: dict[str, Any] = {"broadcast_id": int(bc.id), **stats}
            await self._outbox.append(
                event_type="broadcast.finished",
                payload=payload,
                now=now,
            )
            await self._audit.log(
                actor_id=bc.created_by,
                action="broadcast.finish",
                target_type="broadcast",
                target_id=int(bc.id),
                payload=payload,
                now=now,
            )
            created_by = int(bc.created_by)
            await self._uow.commit()

        # Уведомление админу — вне транзакции.
        try:
            await self._bot.send_text(
                chat_id=created_by,
                text=self._format_summary(int(bc.id), stats),
            )
        except Exception as e:
            log.warning(
                "finalize_broadcast_notify_failed",
                broadcast_id=int(bc.id),
                error=str(e),
            )

        return FinalizeBroadcastResult(finalized=True, stats=stats)

    @staticmethod
    def _format_summary(broadcast_id: int, stats: dict[str, int]) -> str:
        return (
            f"✅ Рассылка #{broadcast_id} завершена.\n\n"
            f"Всего: {stats.get('total', 0)}\n"
            f"Отправлено: {stats.get('sent', 0)}\n"
            f"Заблокировано: {stats.get('blocked', 0)}\n"
            f"Ошибки: {stats.get('failed', 0)}"
        )
