"""Throttle: token-bucket per user_id. Лимит N апдейтов/мин (см. settings)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from dishka import AsyncContainer
from dishka.integrations.aiogram import CONTAINER_NAME
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.logging import get_logger
from app.infrastructure.redis.token_bucket import TokenBucket
from app.presentation.bot.texts.ru import t

log = get_logger(__name__)


class ThrottleMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = data.get("event_from_user") or getattr(event, "from_user", None)
        if from_user is None or getattr(from_user, "is_bot", False):
            return await handler(event, data)

        container: AsyncContainer | None = data.get(CONTAINER_NAME)
        if container is None:
            return await handler(event, data)

        async with container() as req:
            redis: Redis = await req.get(Redis)
            settings: Settings = await req.get(Settings)
            bucket = TokenBucket(redis)
            # rate = cap / 60 сек → ~капля в 2 секунды при cap=30
            rate = settings.max_user_updates_per_min / 60.0
            capacity = settings.max_user_updates_per_min
            wait = await bucket.try_acquire(
                f"throttle:{from_user.id}", rate, capacity
            )

        if wait == 0.0:
            return await handler(event, data)

        # превышен — тихий drop с одноразовым предупреждением
        async with container() as req:
            redis = await req.get(Redis)
            warn_key = f"throttle_warn:{from_user.id}"
            warned = await redis.set(warn_key, b"1", nx=True, ex=60)

        if warned:
            try:
                if isinstance(event, CallbackQuery):
                    await event.answer(t("throttle_warning"), show_alert=False)
                elif isinstance(event, Message):
                    await event.answer(t("throttle_warning"))
            except Exception:  # noqa: BLE001
                log.warning("throttle_notice_failed", uid=from_user.id)
        return None
