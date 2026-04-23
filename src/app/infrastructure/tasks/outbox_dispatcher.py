"""Минимальный outbox-диспетчер.

Забирает из outbox необработанные события (published_at IS NULL) пачкой
`FOR UPDATE SKIP LOCKED`, маршрутизирует их в TaskIQ-задачи по event_type
и отмечает published_at = now().

Маршруты:
- `fanfic.approved`  → `repaginate_chapter(chapter_id)` для каждой главы +
                       `index_fanfic(fic_id)` + fanout уведомлений подписчикам
                       (только для первой публикации / новой главы).
- `fanfic.edited`    → `index_fanfic(fic_id)`
- `fanfic.archived`  → `index_fanfic(fic_id)` (задача сама удалит документ по статусу)
- `report.created`   → no-op (модераторы видят жалобы в своей вкладке).
- `report.handled`   → `notify_moderation_decision(reporter_id, report_id)` при
                       notify_reporter=True.

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
from app.infrastructure.tasks.notifications import (
    notify_author_fic_archived,
    notify_moderation_decision,
    notify_new_chapter,
    notify_new_work,
)
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


async def _enqueue_notify_new_work(author_id: int, fic_id: int) -> None:
    try:
        await notify_new_work.kiq(author_id, fic_id)
    except Exception as e:
        log.warning(
            "outbox_dispatch_notify_new_work_enqueue_failed",
            author_id=author_id,
            fic_id=fic_id,
            error=str(e),
        )


async def _enqueue_notify_new_chapter(author_id: int, fic_id: int, chapter_id: int) -> None:
    try:
        await notify_new_chapter.kiq(author_id, fic_id, chapter_id)
    except Exception as e:
        log.warning(
            "outbox_dispatch_notify_new_chapter_enqueue_failed",
            author_id=author_id,
            fic_id=fic_id,
            chapter_id=chapter_id,
            error=str(e),
        )


async def _enqueue_notify_moderation_decision(user_id: int, report_id: int) -> None:
    try:
        await notify_moderation_decision.kiq(user_id, report_id)
    except Exception as e:
        log.warning(
            "outbox_dispatch_notify_moderation_decision_enqueue_failed",
            user_id=user_id,
            report_id=report_id,
            error=str(e),
        )


async def _enqueue_notify_author_fic_archived(
    author_id: int,
    fic_id: int,
    fic_title: str,
    report_id: int,
    reason_code: str | None,
    moderator_comment: str | None,
) -> None:
    try:
        await notify_author_fic_archived.kiq(
            author_id, fic_id, fic_title, report_id, reason_code, moderator_comment
        )
    except Exception as e:
        log.warning(
            "outbox_dispatch_notify_author_archived_enqueue_failed",
            author_id=author_id,
            fic_id=fic_id,
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

        # Fanout подписчикам:
        #  * first_publish=True → уведомление о новой работе;
        #  * new_chapter_ids — главы, одобренные впервые (добавленные к уже
        #    опубликованной работе), шлём notify_new_chapter для каждой.
        # Чистые правки (edit без новых глав) → new_chapter_ids пустой, fanout нет.
        author_id = payload.get("author_id")
        if fic_id is not None and author_id is not None:
            if bool(payload.get("first_publish")):
                await _enqueue_notify_new_work(int(author_id), int(fic_id))
            else:
                new_chapter_ids = payload.get("new_chapter_ids") or []
                for ch_id in new_chapter_ids:
                    await _enqueue_notify_new_chapter(int(author_id), int(fic_id), int(ch_id))
        return

    if event_type in _INDEX_EVENTS:
        fic_id = payload.get("fic_id")
        if fic_id is not None:
            await _enqueue_index(int(fic_id))
        return

    if event_type == "report.handled":
        if not bool(payload.get("notify_reporter")):
            return
        reporter_id = payload.get("reporter_id")
        report_id = payload.get("report_id")
        if reporter_id is not None and report_id is not None:
            await _enqueue_notify_moderation_decision(int(reporter_id), int(report_id))
        return

    if event_type == "fanfic.archived_by_report":
        author_id = payload.get("author_id")
        fic_id = payload.get("fic_id")
        report_id = payload.get("report_id")
        if author_id is not None and fic_id is not None and report_id is not None:
            await _enqueue_notify_author_fic_archived(
                int(author_id),
                int(fic_id),
                str(payload.get("fic_title") or ""),
                int(report_id),
                payload.get("reason_code"),
                payload.get("moderator_comment"),
            )
        return

    # report.created и прочее — без TaskIQ-задачи, просто маркируем published_at.


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
