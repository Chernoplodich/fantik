"""Периодический тик обновления Prometheus Gauge'ов, которые нельзя посчитать
инкрементально: глубина очередей, возраст outbox, бизнес-счётчики.

Работает как обычная TaskIQ-задача на default broker с cron '* * * * *'.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import (
    ACTIVE_USERS_24H,
    FICS_APPROVED_TOTAL_G,
    MODERATION_QUEUE_DEPTH,
    OUTBOX_OLDEST_PENDING_AGE,
    USERS_TOTAL,
    WORKER_QUEUE_DEPTH,
)
from app.infrastructure.tasks._container import get_worker_container
from app.infrastructure.tasks.broker import broker

log = get_logger(__name__)


async def _refresh_db_gauges(session: AsyncSession) -> None:
    """Один pass по БД для бизнес-метрик."""
    # Moderation queue depth by kind.
    rows = (
        await session.execute(
            text(
                """
                SELECT kind, count(*) AS n
                  FROM moderation_queue
                 WHERE decision IS NULL
                 GROUP BY kind
                """
            )
        )
    ).all()
    seen_kinds: set[str] = set()
    for row in rows:
        kind = str(row.kind)
        MODERATION_QUEUE_DEPTH.labels(kind=kind).set(int(row.n))
        seen_kinds.add(kind)
    # Обнулим старые kind'ы, которые перестали попадать в выборку.
    for known_kind in ("fic_first_publish", "fic_edit", "chapter_add"):
        if known_kind not in seen_kinds:
            MODERATION_QUEUE_DEPTH.labels(kind=known_kind).set(0)

    # Users total + active 24h.
    total = await session.scalar(text("SELECT count(*) FROM users"))
    USERS_TOTAL.set(int(total or 0))

    active = await session.scalar(
        text("SELECT count(*) FROM users WHERE last_seen_at >= now() - interval '24 hours'")
    )
    ACTIVE_USERS_24H.set(int(active or 0))

    approved = await session.scalar(text("SELECT count(*) FROM fanfics WHERE status = 'approved'"))
    FICS_APPROVED_TOTAL_G.set(int(approved or 0))

    # Outbox — возраст самого старого неопубликованного события.
    oldest = await session.scalar(
        text("SELECT min(created_at) FROM outbox WHERE published_at IS NULL")
    )
    if oldest is None:
        OUTBOX_OLDEST_PENDING_AGE.set(0)
    else:
        age = (datetime.now(UTC) - oldest).total_seconds()
        OUTBOX_OLDEST_PENDING_AGE.set(max(0.0, age))


async def _refresh_redis_gauges() -> None:
    """Depth очередей TaskIQ (длина Redis-списка очереди)."""
    settings = get_settings()
    # Не дёргаем Redis-клиент из DI (он REQUEST-scope); простая прямая сессия.
    from redis.asyncio import Redis

    client = Redis.from_url(settings.redis_url_for(settings.redis_taskiq_db))
    try:
        for queue in (settings.taskiq_queue_default, settings.taskiq_queue_broadcast):
            depth = await client.llen(queue)
            WORKER_QUEUE_DEPTH.labels(queue=queue).set(int(depth))
    finally:
        await client.aclose()


@broker.task(
    task_name="metrics_refresh_tick",
    schedule=[{"cron": "* * * * *"}],
)
async def metrics_refresh_tick() -> None:
    """Полный проход обновления Gauge-метрик (раз в минуту)."""
    container = get_worker_container()
    try:
        async with container() as scope:
            session = await scope.get(AsyncSession)
            async with session.begin():
                await _refresh_db_gauges(session)
        await _refresh_redis_gauges()
    except Exception as e:
        log.warning("metrics_refresh_failed", error=str(e))
