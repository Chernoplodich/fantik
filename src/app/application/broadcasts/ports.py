"""Порты application-слоя для рассылок."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.domain.broadcasts.entities import Broadcast
from app.domain.broadcasts.segment import SegmentPlan
from app.domain.broadcasts.value_objects import BroadcastStatus, DeliveryStatus
from app.domain.shared.types import BroadcastId, UserId


@dataclass(kw_only=True)
class Delivery:
    broadcast_id: BroadcastId
    user_id: UserId
    status: DeliveryStatus
    attempts: int
    error_code: str | None
    sent_at: datetime | None


# ---------- result type для copy_message ----------


@dataclass(frozen=True)
class CopyOK:
    """Успешно доставили."""


@dataclass(frozen=True)
class CopyRetryAfter:
    """Telegram попросил подождать N секунд (429)."""

    seconds: float


@dataclass(frozen=True)
class CopyBlocked:
    """Юзер заблокировал бота или чат не существует (403 / chat not found)."""


@dataclass(frozen=True)
class CopyBadRequest:
    """Ошибка, требующая retry/dlq (неверный от запрос, временная проблема)."""

    error_code: str


@dataclass(frozen=True)
class CopyUnknownError:
    """Неизвестная ошибка — retry как CopyBadRequest."""

    error_code: str


CopyResult = CopyOK | CopyRetryAfter | CopyBlocked | CopyBadRequest | CopyUnknownError


# ---------- репозитории ----------


class IBroadcastRepository(Protocol):
    async def create(self, broadcast: Broadcast) -> BroadcastId: ...

    async def get(self, broadcast_id: BroadcastId) -> Broadcast | None: ...

    async def save(self, broadcast: Broadcast) -> None:
        """Сохранить состояние (UPDATE по id)."""
        ...

    async def list_by_creator(self, *, created_by: UserId, limit: int = 20) -> list[Broadcast]: ...

    async def list_by_status(
        self, statuses: list[BroadcastStatus], limit: int = 100
    ) -> list[Broadcast]: ...

    async def scan_ready_to_run(self, *, now: datetime, limit: int = 10) -> list[BroadcastId]:
        """Атомарно взять scheduled-рассылки, у которых scheduled_at <= now.

        Переводит их в `running` (UPDATE ... RETURNING id) через CTE с
        FOR UPDATE SKIP LOCKED — безопасно при параллельных scheduler-тиках.
        """
        ...

    async def update_stats(self, *, broadcast_id: BroadcastId, stats: dict[str, int]) -> None: ...


class IDeliveryRepository(Protocol):
    async def upsert_pending(self, *, broadcast_id: BroadcastId, user_ids: list[UserId]) -> int:
        """Batch INSERT ... ON CONFLICT (broadcast_id, user_id) DO NOTHING.

        Возвращает число реально вставленных строк.
        """
        ...

    async def get_for_update(
        self, *, broadcast_id: BroadcastId, user_id: UserId
    ) -> Delivery | None: ...

    async def save(self, delivery: Delivery) -> None: ...

    async def count_by_status(self, broadcast_id: BroadcastId) -> dict[DeliveryStatus, int]: ...

    def iter_user_ids_by_status(
        self,
        *,
        broadcast_id: BroadcastId,
        statuses: list[DeliveryStatus],
        chunk_size: int = 1000,
    ) -> AsyncIterator[list[UserId]]:
        """Стримить user_id с выбранными статусами — для retry_failed сегмента.

        Async-генератор: `def` без `async`, yield'ит батчи.
        """
        ...


class IUserSegmentReader(Protocol):
    """Резолвер сегмента → AsyncIterator[list[user_id]]."""

    def iter_user_ids(
        self, *, plan: SegmentPlan, chunk_size: int = 1000
    ) -> AsyncIterator[list[UserId]]: ...


# ---------- очередь задач (TaskIQ adapter) ----------


class IBroadcastQueue(Protocol):
    async def enqueue_run(self, broadcast_id: BroadcastId) -> None: ...

    async def enqueue_deliver(
        self, *, broadcast_id: BroadcastId, user_id: UserId, delay_seconds: float = 0.0
    ) -> None: ...

    async def enqueue_finalize(self, broadcast_id: BroadcastId) -> None: ...


# ---------- обёртка над aiogram.copy_message ----------


class IBroadcastBot(Protocol):
    async def copy_message(
        self,
        *,
        chat_id: int,
        from_chat_id: int,
        message_id: int,
        reply_markup: dict[str, Any] | None = None,
        allow_paid_broadcast: bool = False,
        protect_content: bool = False,
    ) -> CopyResult: ...

    async def send_text(self, *, chat_id: int, text: str) -> None:
        """Простое уведомление (итог рассылки и пр.)."""
        ...
