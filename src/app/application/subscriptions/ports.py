"""Порты application-слоя для подписок и уведомлений."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.domain.shared.types import NotificationId, UserId


class ISubscriptionRepository(Protocol):
    async def add_if_absent(
        self, *, subscriber_id: UserId, author_id: UserId, now: datetime
    ) -> bool:
        """Идемпотентный INSERT ... ON CONFLICT DO NOTHING.

        Возвращает True, если вставили новую запись; False, если уже была подписка.
        """
        ...

    async def remove(self, *, subscriber_id: UserId, author_id: UserId) -> bool:
        """Возвращает True, если удалили строку; False, если не было."""
        ...

    async def exists(self, *, subscriber_id: UserId, author_id: UserId) -> bool: ...

    def iter_subscriber_ids(
        self, *, author_id: UserId, chunk_size: int = 500
    ) -> AsyncIterator[list[UserId]]:
        """Стримить subscriber_id чанками (для fanout уведомлений).

        Это async-генератор: `def` без `async`, возвращает AsyncIterator.
        Реализация использует `yield` внутри `async def` — Python Protocol
        описывает контракт через сигнатуру, не тело.
        """
        ...


class INotificationRepository(Protocol):
    async def create(
        self,
        *,
        user_id: UserId,
        kind: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> NotificationId: ...

    async def create_many(
        self,
        *,
        user_ids: list[UserId],
        kind: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> list[NotificationId]:
        """Batch-вставка: один INSERT ... RETURNING id на всех получателей."""
        ...

    async def mark_sent(self, *, notification_id: NotificationId, now: datetime) -> None: ...


@dataclass(frozen=True, kw_only=True)
class DeliverOneCommand:
    """DTO для постановки задачи deliver_notification."""

    user_id: UserId
    notification_id: NotificationId
    kind: str
    payload: dict[str, Any]


class INotificationQueue(Protocol):
    """Адаптер TaskIQ-очереди уведомлений.

    Методы `enqueue_fanout_*` ставят задачу-«раздатчик», которая сама внутри
    use case'а `NotifySubscribersUseCase` делает батч-вставку в `notifications`
    и рассылает задачи `deliver_notification` каждому подписчику.

    `enqueue_deliver_one` — прямая отправка уведомления одному пользователю
    (уже созданная запись в `notifications`).
    """

    async def enqueue_fanout_new_chapter(
        self, *, author_id: UserId, fic_id: int, chapter_id: int
    ) -> None: ...

    async def enqueue_fanout_new_work(self, *, author_id: UserId, fic_id: int) -> None: ...

    async def enqueue_deliver_one(self, cmd: DeliverOneCommand) -> None: ...
