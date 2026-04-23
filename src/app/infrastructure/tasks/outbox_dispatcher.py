"""Минимальный outbox-диспетчер.

Забирает из outbox необработанные события (published_at IS NULL) пачкой
`FOR UPDATE SKIP LOCKED`, маршрутизирует их в TaskIQ-задачи по event_type
и отмечает published_at = now().

Маршруты:
- `fanfic.approved`  → `repaginate_chapter(chapter_id)` для каждой главы + `index_fanfic(fic_id)`
- `fanfic.edited`    → `index_fanfic(fic_id)`
- `fanfic.archived`  → `index_fanfic(fic_id)` (задача сама удалит документ по статусу)

Остальные события пропускаются с пометкой published_at, чтобы не копились.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infrastructure.tasks._container import get_worker_container
from app.infrastructure.tasks.broker import broker
from app.infrastructure.tasks.indexing import index_fanfic
from app.infrastructure.tasks.repagination import repaginate_chapter

log = get_logger(__name__)

_BATCH_SIZE = 50

_INDEX_EVENTS = frozenset({"fanfic.approved", "fanfic.edited", "fanfic.archived"})


async def _enqueue_index(fic_id: int) -> None:
    try:
        await index_fanfic.kiq(fic_id)
    except Exception as e:
        log.warning("outbox_dispatch_index_enqueue_failed", fic_id=fic_id, error=str(e))


async def _enqueue_repaginate(chapter_id: int) -> None:
    try:
        await repaginate_chapter.kiq(chapter_id)
    except Exception as e:
        log.warning(
            "outbox_dispatch_repaginate_enqueue_failed",
            chapter_id=chapter_id,
            error=str(e),
        )


async def _dispatch_one(event_type: str, payload: dict[str, Any]) -> None:
    if event_type == "fanfic.approved":
        chapter_ids = payload.get("chapter_ids") or []
        for ch_id in chapter_ids:
            await _enqueue_repaginate(int(ch_id))
        fic_id = payload.get("fic_id")
        if fic_id is not None:
            await _enqueue_index(int(fic_id))
        return

    if event_type in _INDEX_EVENTS:
        fic_id = payload.get("fic_id")
        if fic_id is not None:
            await _enqueue_index(int(fic_id))
        return

    # неизвестные/не-индекс события — просто маркируем как обработанные, чтобы не копились


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
        except Exception as e:
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
