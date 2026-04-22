"""Минимальный outbox-диспетчер.

Забирает из outbox необработанные события (published_at IS NULL) пачкой
`FOR UPDATE SKIP LOCKED`, маршрутизирует их в TaskIQ-задачи по event_type
и отмечает published_at = now().

Сейчас понимает:
- `fanfic.approved` → для каждого chapter_id из payload ставит `repaginate_chapter`.

Остальные события просто пропускает с пометкой published_at, чтобы они не
копились. Расширяем по мере появления обработчиков в следующих этапах.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.tasks._container import get_worker_container
from app.infrastructure.tasks.broker import broker
from app.infrastructure.tasks.repagination import repaginate_chapter

log = get_logger(__name__)

_BATCH_SIZE = 50


async def _dispatch_one(event_type: str, payload: dict[str, Any]) -> None:
    if event_type == "fanfic.approved":
        chapter_ids = payload.get("chapter_ids") or []
        for ch_id in chapter_ids:
            try:
                await repaginate_chapter.kiq(int(ch_id))
            except Exception as e:  # noqa: BLE001 — не роняем диспетчер
                log.warning(
                    "outbox_dispatch_enqueue_failed",
                    event_type=event_type,
                    chapter_id=ch_id,
                    error=str(e),
                )


async def _process_batch(session: AsyncSession) -> int:
    stmt = text(
        """
        SELECT id, event_type, payload
          FROM outbox
         WHERE published_at IS NULL
         ORDER BY id
         LIMIT :limit
         FOR UPDATE SKIP LOCKED
        """
    )
    rows = (await session.execute(stmt, {"limit": _BATCH_SIZE})).all()
    if not rows:
        return 0

    processed_ids: list[int] = []
    for row in rows:
        event_id = int(row.id)
        event_type = str(row.event_type)
        payload = dict(row.payload or {})
        try:
            await _dispatch_one(event_type, payload)
        except Exception as e:  # noqa: BLE001
            log.exception(
                "outbox_dispatch_failed",
                event_id=event_id,
                event_type=event_type,
                error=str(e),
            )
            continue
        processed_ids.append(event_id)

    if processed_ids:
        await session.execute(
            text("UPDATE outbox SET published_at = :now WHERE id = ANY(:ids)"),
            {"now": datetime.now(UTC), "ids": processed_ids},
        )
    return len(processed_ids)


@broker.task(
    task_name="outbox_dispatch_tick",
    schedule=[{"cron": "* * * * *"}],  # раз в минуту — LabelScheduleSource
)
async def outbox_dispatch_tick() -> int:
    """Одна итерация диспетчера: забрать батч, разослать, пометить."""
    container = get_worker_container()
    total = 0
    async with container() as scope:
        session = await scope.get(AsyncSession)
        async with session.begin():
            total = await _process_batch(session)
    if total:
        log.info("outbox_dispatch_tick_done", processed=total)
    return total
