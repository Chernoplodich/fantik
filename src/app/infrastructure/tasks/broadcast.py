"""TaskIQ-задачи рассылок: run_broadcast / deliver_one / finalize_broadcast.

Живут на `broadcast_broker` — отдельная очередь воркеров с глобальным
token-bucket 25 msg/s (или 1000 при allow_paid_broadcast).
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.application.broadcasts.deliver_one import (
    DeliverOneCommand,
    DeliverOneUseCase,
    DeliveryRetryRequestedError,
)
from app.application.broadcasts.enumerate_recipients import (
    EnumerateRecipientsCommand,
    EnumerateRecipientsUseCase,
)
from app.application.broadcasts.finalize import (
    FinalizeBroadcastCommand,
    FinalizeBroadcastUseCase,
)
from app.application.broadcasts.ports import (
    IBroadcastQueue,
    IBroadcastRepository,
    IDeliveryRepository,
)
from app.application.shared.ports import UnitOfWork
from app.core.logging import get_logger
from app.domain.broadcasts.value_objects import BroadcastStatus
from app.domain.shared.types import BroadcastId, UserId
from app.infrastructure.tasks._container import get_worker_container
from app.infrastructure.tasks.broker import broadcast_broker

log = get_logger(__name__)


_DELIVERY_BATCH = 1000


@broadcast_broker.task(task_name="run_broadcast")
async def run_broadcast(broadcast_id: int) -> int:
    """Резолвит получателей, вставляет pending, ставит deliver_one задачи.

    Идемпотентна: на старте проверяет статус (если cancelled — no-op).
    ON CONFLICT DO NOTHING в upsert_pending не создаст дубли при рестарте.

    ВАЖНО: upsert_pending коммитим ДО enqueue_deliver, иначе worker подхватит
    задачу быстрее, чем комитнутся строки, и увидит deliver_one_no_pending_row.
    """
    bid = BroadcastId(int(broadcast_id))
    container = get_worker_container()

    # 1) Статус + enumerate — отдельный scope.
    async with container() as scope:
        broadcasts: IBroadcastRepository = await scope.get(IBroadcastRepository)
        enumerate_uc: EnumerateRecipientsUseCase = await scope.get(EnumerateRecipientsUseCase)
        bc = await broadcasts.get(bid)
        if bc is None:
            log.warning("run_broadcast_not_found", broadcast_id=int(bid))
            return 0
        if bc.status in (
            BroadcastStatus.CANCELLED,
            BroadcastStatus.FINISHED,
            BroadcastStatus.FAILED,
        ):
            log.info(
                "run_broadcast_skip_terminal",
                broadcast_id=int(bid),
                status=bc.status.value,
            )
            return 0
        recipient_iter = await enumerate_uc(
            EnumerateRecipientsCommand(broadcast_id=int(bid), chunk_size=_DELIVERY_BATCH)
        )
        # Собираем чанки в памяти — stream держит session; закроем scope
        # и дальше будем работать чанками в отдельных транзакциях.
        chunks: list[list[UserId]] = []
        async for chunk in recipient_iter:
            if chunk:
                chunks.append([UserId(int(u)) for u in chunk])

    # 2) Для каждого чанка — новый scope и отдельная транзакция:
    #    insert + commit + enqueue. Коммитим ДО enqueue, чтобы worker увидел row.
    total_enqueued = 0
    for chunk in chunks:
        async with container() as scope:
            broadcasts = await scope.get(IBroadcastRepository)
            deliveries: IDeliveryRepository = await scope.get(IDeliveryRepository)
            uow: UnitOfWork = await scope.get(UnitOfWork)
            queue: IBroadcastQueue = await scope.get(IBroadcastQueue)

            # Проверка отмены между чанками.
            bc = await broadcasts.get(bid)
            if bc is None or bc.status == BroadcastStatus.CANCELLED:
                log.info("run_broadcast_cancelled_midway", broadcast_id=int(bid))
                return total_enqueued

            async with uow:
                inserted = await deliveries.upsert_pending(broadcast_id=bid, user_ids=chunk)
                await uow.commit()

            log.info(
                "run_broadcast_chunk",
                broadcast_id=int(bid),
                chunk_size=len(chunk),
                inserted=int(inserted),
            )
            # Параллельная постановка задач: Redis pool сам раскидает по
            # свободным соединениям. На pool=10 это 10x ускорение vs sequential,
            # критично для рассылок на 10k+ юзеров.
            _ENQUEUE_BATCH = 100
            for i in range(0, len(chunk), _ENQUEUE_BATCH):
                sub = chunk[i : i + _ENQUEUE_BATCH]
                await asyncio.gather(
                    *[queue.enqueue_deliver(broadcast_id=bid, user_id=uid) for uid in sub]
                )
                total_enqueued += len(sub)

    log.info("run_broadcast_done", broadcast_id=int(bid), enqueued=total_enqueued)
    return total_enqueued


@broadcast_broker.task(task_name="deliver_one", retry_on_error=False)
async def deliver_one(broadcast_id: int, user_id: int) -> bool:
    """Доставка одного сообщения — идемпотентна.

    Инкапсулирует DeliverOneUseCase, ловит `DeliveryRetryRequestedError`
    и заводит новую задачу с задержкой.
    """
    container = get_worker_container()
    try:
        async with container() as scope:
            uc: DeliverOneUseCase = await scope.get(DeliverOneUseCase)
            result = await uc(
                DeliverOneCommand(broadcast_id=int(broadcast_id), user_id=int(user_id))
            )
        return bool(result.sent)
    except DeliveryRetryRequestedError as exc:
        # Ждём и перезаводим задачу — тот же broker, тот же воркер её поднимет.
        log.info(
            "deliver_one_retry",
            broadcast_id=int(broadcast_id),
            user_id=int(user_id),
            delay=exc.delay_seconds,
        )
        await asyncio.sleep(exc.delay_seconds)
        await deliver_one.kiq(int(broadcast_id), int(user_id))
        return False


@broadcast_broker.task(task_name="finalize_broadcast")
async def finalize_broadcast(broadcast_id: int) -> dict[str, Any]:
    """Периодически — если pending=0, перевести рассылку в finished."""
    container = get_worker_container()
    async with container() as scope:
        uc: FinalizeBroadcastUseCase = await scope.get(FinalizeBroadcastUseCase)
        result = await uc(FinalizeBroadcastCommand(broadcast_id=int(broadcast_id)))
    return {
        "finalized": bool(result.finalized),
        "stats": dict(result.stats),
    }
