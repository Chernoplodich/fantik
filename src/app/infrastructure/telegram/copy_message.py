"""Обёртка `bot.copy_message` с классификацией ошибок для broadcast-доставки.

Интегрирована с `BroadcastFloodLock`: перед КАЖДЫМ вызовом TG-API проверяем
глобальный flag — если был 429, все воркеры синхронно ждут до истечения
retry_after. Это критично: при 429 весь бот блокируется Telegram'ом, и
остальные параллельные задачи без этого спавнятся и усугубляют ban.
"""

from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardMarkup

from app.application.broadcasts.ports import (
    CopyBadRequest,
    CopyBlocked,
    CopyOK,
    CopyResult,
    CopyRetryAfter,
    CopyUnknownError,
    IBroadcastBot,
)
from app.core.logging import get_logger
from app.infrastructure.redis.broadcast_flood_lock import BroadcastFloodLock

log = get_logger(__name__)


# Под-строки в TelegramBadRequest.message, которые эквивалентны «блок»:
# chat/user не существует/удалён/бот кикнут. retry не спасёт.
_BLOCKED_MARKERS = (
    "chat not found",
    "user is deactivated",
    "bot was blocked by the user",
    "bot was kicked",
    "user is deleted",
    "peer_id_invalid",
)


class AiogramBroadcastBot(IBroadcastBot):
    def __init__(self, bot: Bot, flood_lock: BroadcastFloodLock) -> None:
        self._bot = bot
        self._flood = flood_lock

    async def copy_message(
        self,
        *,
        chat_id: int,
        from_chat_id: int,
        message_id: int,
        reply_markup: dict[str, Any] | None = None,
        allow_paid_broadcast: bool = False,
        protect_content: bool = False,
    ) -> CopyResult:
        markup: InlineKeyboardMarkup | None = None
        if reply_markup:
            # aiogram валидирует структуру через pydantic — кидает ValidationError
            # при неверном формате; ловим как BadRequest (не ретраем бесконечно).
            try:
                markup = InlineKeyboardMarkup.model_validate(reply_markup)
            except Exception as e:
                return CopyBadRequest(error_code=f"invalid_keyboard: {e}")

        kwargs: dict[str, Any] = {
            "chat_id": int(chat_id),
            "from_chat_id": int(from_chat_id),
            "message_id": int(message_id),
            "reply_markup": markup,
            "protect_content": bool(protect_content),
        }
        if allow_paid_broadcast:
            # allow_paid_broadcast поддерживается в aiogram 3.27+ (Bot API 7.x).
            # Передаём только если True, чтобы не ломать старые Bot API, если
            # фича не включена на этом боте.
            kwargs["allow_paid_broadcast"] = True

        # Глобальный flood-lock: если другой воркер поймал 429, ждём вместе
        # с ним. Без этого параллельные задачи спавнятся и удлиняют ban.
        await self._flood.wait_if_blocked()

        try:
            await self._bot.copy_message(**kwargs)
        except TelegramRetryAfter as e:
            # Заглушаем ВСЕ воркеры на retry_after секунд (глобальный flag).
            await self._flood.set_flood(float(e.retry_after))
            log.warning(
                "broadcast_flood_triggered",
                retry_after=int(e.retry_after),
                chat_id=int(chat_id),
            )
            return CopyRetryAfter(seconds=float(e.retry_after))
        except TelegramForbiddenError:
            return CopyBlocked()
        except TelegramBadRequest as e:
            msg = str(e.message or e).lower()
            if any(marker in msg for marker in _BLOCKED_MARKERS):
                return CopyBlocked()
            return CopyBadRequest(error_code=str(e.message or "bad_request"))
        except TelegramAPIError as e:
            return CopyUnknownError(error_code=str(e))
        return CopyOK()

    async def send_text(self, *, chat_id: int, text: str) -> None:
        await self._flood.wait_if_blocked()
        try:
            await self._bot.send_message(chat_id=int(chat_id), text=text)
        except TelegramRetryAfter as e:
            await self._flood.set_flood(float(e.retry_after))
            log.warning(
                "broadcast_summary_flood",
                chat_id=int(chat_id),
                retry_after=int(e.retry_after),
            )
        except TelegramForbiddenError:
            # Админ заблокировал бота — маловероятно; silent skip.
            log.warning("broadcast_summary_forbidden", chat_id=int(chat_id))
        except TelegramAPIError as e:
            log.warning("broadcast_summary_failed", chat_id=int(chat_id), error=str(e))
