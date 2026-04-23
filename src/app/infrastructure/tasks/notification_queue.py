"""Адаптер INotificationQueue → TaskIQ."""

from __future__ import annotations

import json

from app.application.subscriptions.ports import (
    DeliverOneCommand,
    INotificationQueue,
)
from app.domain.shared.types import UserId
from app.infrastructure.tasks.notifications import (
    deliver_notification,
    notify_new_chapter,
    notify_new_work,
)


class TaskiqNotificationQueue(INotificationQueue):
    async def enqueue_fanout_new_chapter(
        self, *, author_id: UserId, fic_id: int, chapter_id: int
    ) -> None:
        await notify_new_chapter.kiq(int(author_id), int(fic_id), int(chapter_id))

    async def enqueue_fanout_new_work(self, *, author_id: UserId, fic_id: int) -> None:
        await notify_new_work.kiq(int(author_id), int(fic_id))

    async def enqueue_deliver_one(self, cmd: DeliverOneCommand) -> None:
        await deliver_notification.kiq(
            int(cmd.user_id),
            int(cmd.notification_id),
            cmd.kind,
            json.dumps(cmd.payload, ensure_ascii=False),
        )
