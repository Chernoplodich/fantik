"""Use case: fanout уведомлений подписчикам автора.

Вызывается из TaskIQ-задач `notify_new_work` / `notify_new_chapter`.

Идея:
  1. Резолвит автора и фик/главу (для кэша заголовка в payload уведомления).
  2. Стримит subscriber_id из `subscriptions` по `author_id` чанками.
  3. Для каждого чанка делает batch-INSERT в `notifications` (один запрос на N
     строк), затем ставит задачи `deliver_notification` в TaskIQ.

Отдельная транзакция на чанк — чтобы падение на середине fanout не откатывало
уже отправленные записи. На уровне delivery 403 обрабатывается в самой задаче
(silent skip).

Почему не пишем через outbox: outbox — для транзакционно-гарантированной
публикации единичного события. Здесь мы уже в задаче, вызванной по такому
событию, и наша работа — конвертировать один высокоуровневый факт в N
доставок.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.application.fanfics.ports import IChapterRepository, IFanficRepository
from app.application.shared.ports import UnitOfWork
from app.application.subscriptions.ports import (
    DeliverOneCommand,
    INotificationQueue,
    INotificationRepository,
    ISubscriptionRepository,
)
from app.core.clock import Clock
from app.core.errors import NotFoundError
from app.core.logging import get_logger
from app.domain.fanfics.value_objects import FicStatus
from app.domain.shared.types import ChapterId, FanficId, UserId

log = get_logger(__name__)


NOTIF_KIND_NEW_WORK = "new_work_from_author"
NOTIF_KIND_NEW_CHAPTER = "new_chapter_from_author"


@dataclass(frozen=True, kw_only=True)
class NotifySubscribersCommand:
    author_id: int
    fic_id: int
    chapter_id: int | None  # None для new_work; id новой главы для new_chapter
    kind: str  # NOTIF_KIND_NEW_WORK | NOTIF_KIND_NEW_CHAPTER


@dataclass(frozen=True, kw_only=True)
class NotifySubscribersResult:
    notifications_created: int


_CHUNK_SIZE = 100


class NotifySubscribersUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        subscriptions: ISubscriptionRepository,
        notifications: INotificationRepository,
        fanfics: IFanficRepository,
        chapters: IChapterRepository,
        notif_queue: INotificationQueue,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._subs = subscriptions
        self._notifs = notifications
        self._fanfics = fanfics
        self._chapters = chapters
        self._queue = notif_queue
        self._clock = clock

    async def __call__(self, cmd: NotifySubscribersCommand) -> NotifySubscribersResult:
        fic = await self._fanfics.get(FanficId(cmd.fic_id))
        if fic is None:
            raise NotFoundError("Фик не найден.")
        if fic.status != FicStatus.APPROVED:
            # Фик мог быть archived между отправкой события и обработкой.
            # Тогда уведомления не отправляем.
            log.info(
                "notify_fanout_skipped_not_approved",
                fic_id=int(fic.id),
                status=fic.status.value,
            )
            return NotifySubscribersResult(notifications_created=0)

        chapter_number: int | None = None
        chapter_title: str | None = None
        if cmd.chapter_id is not None and cmd.kind == NOTIF_KIND_NEW_CHAPTER:
            ch = await self._chapters.get(ChapterId(cmd.chapter_id))
            if ch is None:
                log.warning("notify_fanout_chapter_missing", chapter_id=cmd.chapter_id)
                return NotifySubscribersResult(notifications_created=0)
            chapter_number = int(ch.number)
            chapter_title = str(ch.title)

        payload: dict[str, Any] = {
            "fic_id": int(fic.id),
            "fic_title": str(fic.title),
            "author_id": int(fic.author_id),
        }
        if chapter_number is not None:
            payload["chapter_id"] = int(cmd.chapter_id) if cmd.chapter_id else 0
            payload["chapter_number"] = chapter_number
            payload["chapter_title"] = chapter_title or ""

        total = 0
        author_id = UserId(cmd.author_id)
        async for chunk in self._subs.iter_subscriber_ids(
            author_id=author_id, chunk_size=_CHUNK_SIZE
        ):
            if not chunk:
                continue
            # Автора из выборки убираем — на случай, если в БД случайно оказалась
            # «подписка на себя» (CHECK-constraint защищает, но перестраховка).
            recipients = [uid for uid in chunk if uid != author_id]
            if not recipients:
                continue
            async with self._uow:
                ids = await self._notifs.create_many(
                    user_ids=recipients,
                    kind=cmd.kind,
                    payload=payload,
                    now=self._clock.now(),
                )
                await self._uow.commit()
            for user_id, notif_id in zip(recipients, ids, strict=True):
                await self._queue.enqueue_deliver_one(
                    DeliverOneCommand(
                        user_id=user_id,
                        notification_id=notif_id,
                        kind=cmd.kind,
                        payload=payload,
                    )
                )
            total += len(ids)

        log.info(
            "notify_fanout_done",
            author_id=int(author_id),
            fic_id=int(fic.id),
            chapter_id=cmd.chapter_id,
            kind=cmd.kind,
            total=total,
        )
        return NotifySubscribersResult(notifications_created=total)
