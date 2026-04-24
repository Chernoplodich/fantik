"""Use case: идемпотентная доставка одного сообщения одному получателю.

Вызывается из TaskIQ-задачи `deliver_one` на broadcast_broker. Сам
acquire'ит глобальный token-bucket (25/s по умолчанию, 1000/s при
allow_paid_broadcast).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.application.broadcasts.ports import (
    CopyBadRequest,
    CopyBlocked,
    CopyOK,
    CopyRetryAfter,
    CopyUnknownError,
    Delivery,
    IBroadcastBot,
    IBroadcastRepository,
    IDeliveryRepository,
)
from app.application.shared.ports import UnitOfWork
from app.application.users.ports import IUserRepository
from app.core.clock import Clock
from app.core.config import Settings
from app.core.logging import get_logger
from app.core.metrics import BROADCAST_BUCKET_WAIT, BROADCAST_DELIVERIES
from app.domain.broadcasts.value_objects import (
    FINAL_DELIVERY_STATUSES,
    BroadcastStatus,
    DeliveryStatus,
)
from app.domain.shared.types import BroadcastId, UserId

if TYPE_CHECKING:
    from app.infrastructure.redis.token_bucket import TokenBucket


log = get_logger(__name__)


BROADCAST_BUCKET_KEY = "broadcast:global"


class DeliveryRetryRequestedError(Exception):
    """Сигнал TaskIQ-задаче: нужно requeue через `delay_seconds` секунд.

    `increment_attempts`=False — не увеличиваем счётчик попыток (например,
    при 429). Иначе инкрементируем.
    """

    def __init__(self, delay_seconds: float, *, increment_attempts: bool) -> None:
        super().__init__(f"retry after {delay_seconds}s")
        self.delay_seconds = float(delay_seconds)
        self.increment_attempts = bool(increment_attempts)


@dataclass(frozen=True, kw_only=True)
class DeliverOneCommand:
    broadcast_id: int
    user_id: int


@dataclass(frozen=True, kw_only=True)
class DeliverOneResult:
    sent: bool
    status: DeliveryStatus


class DeliverOneUseCase:
    def __init__(
        self,
        uow: UnitOfWork,
        broadcasts: IBroadcastRepository,
        deliveries: IDeliveryRepository,
        users: IUserRepository,
        bot: IBroadcastBot,
        bucket: TokenBucket,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._uow = uow
        self._broadcasts = broadcasts
        self._deliveries = deliveries
        self._users = users
        self._bot = bot
        self._bucket = bucket
        self._settings = settings
        self._clock = clock

    async def __call__(self, cmd: DeliverOneCommand) -> DeliverOneResult:
        broadcast_id = BroadcastId(int(cmd.broadcast_id))
        user_id = UserId(int(cmd.user_id))

        # 1) lock delivery, проверить идемпотентность.
        async with self._uow:
            delivery = await self._deliveries.get_for_update(
                broadcast_id=broadcast_id, user_id=user_id
            )
            if delivery is None:
                # Не должно случаться: run_broadcast вставил pending перед enqueue.
                log.warning(
                    "deliver_one_no_pending_row",
                    broadcast_id=int(broadcast_id),
                    user_id=int(user_id),
                )
                await self._uow.commit()
                return DeliverOneResult(sent=False, status=DeliveryStatus.FAILED)

            if delivery.status in FINAL_DELIVERY_STATUSES:
                # Уже доставлено/заблокировано — ничего не делаем.
                await self._uow.commit()
                return DeliverOneResult(sent=False, status=delivery.status)

            broadcast = await self._broadcasts.get(broadcast_id)
            if broadcast is None:
                await self._uow.commit()
                return DeliverOneResult(sent=False, status=DeliveryStatus.FAILED)

            if broadcast.status == BroadcastStatus.CANCELLED:
                # Рассылка отменена — помечаем pending как failed('cancelled').
                delivery.status = DeliveryStatus.FAILED
                delivery.error_code = "cancelled"
                await self._deliveries.save(delivery)
                await self._uow.commit()
                return DeliverOneResult(sent=False, status=DeliveryStatus.FAILED)

            source_chat_id = broadcast.source_chat_id
            source_message_id = broadcast.source_message_id
            keyboard = broadcast.keyboard
            allow_paid = bool(self._settings.allow_paid_broadcast)
            await self._uow.commit()

        # 2) acquire token bucket (вне транзакции).
        if allow_paid:
            rate = float(self._settings.broadcast_rate_paid)
            capacity = int(self._settings.broadcast_rate_paid_capacity)
        else:
            rate = float(self._settings.broadcast_rate)
            capacity = int(self._settings.broadcast_rate_capacity)
        import time as _time

        _bucket_start = _time.monotonic()
        await self._bucket.acquire(BROADCAST_BUCKET_KEY, rate, capacity)
        BROADCAST_BUCKET_WAIT.observe(_time.monotonic() - _bucket_start)

        reply_markup: dict[str, Any] | None = None
        if keyboard:
            reply_markup = {"inline_keyboard": keyboard}

        # 3) copy_message через обёртку.
        result = await self._bot.copy_message(
            chat_id=int(user_id),
            from_chat_id=int(source_chat_id),
            message_id=int(source_message_id),
            reply_markup=reply_markup,
            allow_paid_broadcast=allow_paid,
        )

        # 4) интерпретация результата + UPDATE delivery.
        async with self._uow:
            fresh = await self._deliveries.get_for_update(
                broadcast_id=broadcast_id, user_id=user_id
            )
            if fresh is None:
                await self._uow.commit()
                return DeliverOneResult(sent=False, status=DeliveryStatus.FAILED)

            out = self._apply_result(fresh, result)
            await self._deliveries.save(fresh)
            # Если заблокировали бота — помечаем юзера, чтобы сегмент-резолвер
            # не брал его в следующих рассылках.
            if isinstance(result, CopyBlocked):
                await self._users.mark_bot_blocked(user_id)
            await self._uow.commit()

        return out

    def _apply_result(
        self,
        delivery: Delivery,
        result: CopyOK | CopyRetryAfter | CopyBlocked | CopyBadRequest | CopyUnknownError,
    ) -> DeliverOneResult:
        if isinstance(result, CopyOK):
            delivery.status = DeliveryStatus.SENT
            delivery.sent_at = self._clock.now()
            delivery.error_code = None
            BROADCAST_DELIVERIES.labels(status="sent").inc()
            return DeliverOneResult(sent=True, status=DeliveryStatus.SENT)

        if isinstance(result, CopyBlocked):
            delivery.status = DeliveryStatus.BLOCKED
            delivery.error_code = "blocked"
            BROADCAST_DELIVERIES.labels(status="blocked").inc()
            return DeliverOneResult(sent=False, status=DeliveryStatus.BLOCKED)

        if isinstance(result, CopyRetryAfter):
            # 429 — не увеличиваем attempts, просим requeue с jitter'ом
            # (чтобы параллельные задачи не проснулись все разом).
            import secrets

            jitter = 0.2 + secrets.randbelow(1300) / 1000.0  # 0.2..1.5s
            raise DeliveryRetryRequestedError(
                delay_seconds=float(result.seconds) + jitter,
                increment_attempts=False,
            )

        # BadRequest / UnknownError — attempts += 1, retry до max_attempts.
        delivery.attempts = int(delivery.attempts) + 1
        error_code = (
            result.error_code
            if isinstance(result, CopyBadRequest | CopyUnknownError)
            else "unknown"
        )
        delivery.error_code = error_code[:200] if error_code else None

        max_attempts = int(self._settings.broadcast_delivery_max_attempts)
        if delivery.attempts >= max_attempts:
            delivery.status = DeliveryStatus.FAILED
            BROADCAST_DELIVERIES.labels(status="failed").inc()
            return DeliverOneResult(sent=False, status=DeliveryStatus.FAILED)

        # Сохраним инкремент и поднимем retry.
        delay = float(2**delivery.attempts)
        # Делаем delivery pending, чтобы повторный вызов не стопанулся
        # проверкой на FINAL_DELIVERY_STATUSES.
        delivery.status = DeliveryStatus.PENDING
        raise DeliveryRetryRequestedError(delay_seconds=delay, increment_attempts=True)
