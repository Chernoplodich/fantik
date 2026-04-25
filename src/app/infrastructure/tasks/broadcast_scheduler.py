"""Периодические scheduler-задачи для админского слоя.

Все task'и декорированы `@broker.task(schedule=[{"cron": ...}])` и
подхватываются `LabelScheduleSource`. Важно: они живут на default broker,
а сами запускают задачи на broadcast_broker через TaskiqBroadcastQueue.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.broadcasts.ports import IBroadcastQueue, IBroadcastRepository
from app.application.moderation.release_stale_locks import ReleaseStaleLocksUseCase
from app.core.clock import Clock
from app.core.logging import get_logger
from app.domain.broadcasts.value_objects import BroadcastStatus
from app.infrastructure.db.repositories.partition_maintenance import (
    MATERIALIZED_VIEWS,
    PartitionMaintenanceRepository,
)
from app.infrastructure.tasks._container import get_worker_container
from app.infrastructure.tasks.broker import broker

log = get_logger(__name__)


@broker.task(
    task_name="broadcast_tick",
    schedule=[{"cron": "* * * * *"}],
)
async def broadcast_tick() -> int:
    """Каждую минуту — забрать scheduled-рассылки, перевести в running, запустить."""
    container = get_worker_container()
    total = 0
    async with container() as scope:
        broadcasts: IBroadcastRepository = await scope.get(IBroadcastRepository)
        queue: IBroadcastQueue = await scope.get(IBroadcastQueue)
        clock: Clock = await scope.get(Clock)
        session = await scope.get(AsyncSession)
        async with session.begin():
            ids = await broadcasts.scan_ready_to_run(now=clock.now(), limit=10)
        for bid in ids:
            try:
                await queue.enqueue_run(bid)
                total += 1
            except Exception as e:
                log.warning(
                    "broadcast_tick_enqueue_failed",
                    broadcast_id=int(bid),
                    error=str(e),
                )
    if total:
        log.info("broadcast_tick_launched", count=total)
    return total


@broker.task(
    task_name="finalize_running_broadcasts_tick",
    schedule=[{"cron": "* * * * *"}],
)
async def finalize_running_broadcasts_tick() -> int:
    """Каждую минуту — для всех running-рассылок поставить finalize_broadcast."""
    container = get_worker_container()
    total = 0
    async with container() as scope:
        broadcasts: IBroadcastRepository = await scope.get(IBroadcastRepository)
        queue: IBroadcastQueue = await scope.get(IBroadcastQueue)
        running = await broadcasts.list_by_status([BroadcastStatus.RUNNING], limit=50)
        for bc in running:
            try:
                await queue.enqueue_finalize(bc.id)
                total += 1
            except Exception as e:
                log.warning(
                    "finalize_tick_enqueue_failed",
                    broadcast_id=int(bc.id),
                    error=str(e),
                )
    return total


@broker.task(
    task_name="release_stale_mq_locks_tick",
    schedule=[{"cron": "* * * * *"}],
)
async def release_stale_mq_locks_tick() -> int:
    """Каждую минуту — снять протухшие lock'и в moderation_queue."""
    container = get_worker_container()
    async with container() as scope:
        uc: ReleaseStaleLocksUseCase = await scope.get(ReleaseStaleLocksUseCase)
        released = await uc()
    if released:
        log.info("release_stale_mq_locks_tick_done", released=int(released))
    return int(released)


@broker.task(
    task_name="create_monthly_partitions_tick",
    schedule=[{"cron": "0 3 * * *"}],
)
async def create_monthly_partitions_tick() -> int:
    """Раз в сутки (03:00 UTC) создать партиции tracking_events на 2 месяца вперёд."""
    container = get_worker_container()
    async with container() as scope:
        session = await scope.get(AsyncSession)
        repo = PartitionMaintenanceRepository(session)
        async with session.begin():
            created = await repo.create_tracking_events_partitions(months_ahead=2)
    log.info("create_monthly_partitions_tick_done", months_planned=int(created))
    return int(created)


@broker.task(
    task_name="refresh_materialized_views_tick",
    schedule=[{"cron": "*/10 * * * *"}],
)
async def refresh_materialized_views_tick() -> int:
    """Раз в 10 минут — REFRESH MATERIALIZED VIEW CONCURRENTLY для всех MV.

    Падение одного MV не останавливает остальные: логируем warning и едем дальше.
    """
    container = get_worker_container()
    refreshed = 0
    async with container() as scope:
        session = await scope.get(AsyncSession)
        repo = PartitionMaintenanceRepository(session)
        for mv in MATERIALIZED_VIEWS:
            try:
                # REFRESH MATERIALIZED VIEW CONCURRENTLY не может быть в
                # transaction block — требует autocommit.
                async with session.begin():
                    await repo.refresh_materialized_view(mv)
                refreshed += 1
            except Exception as e:
                log.warning("refresh_mv_failed", mv=mv, error=str(e))
    log.info("refresh_materialized_views_tick_done", refreshed=refreshed)
    return refreshed
