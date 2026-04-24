"""Logging middleware: биндит контекст к structlog + экспонирует метрики обновлений/хендлеров."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineQuery,
    Message,
    TelegramObject,
    Update,
)

from app.core.logging import get_logger
from app.core.metrics import BOT_HANDLER_ERRORS, BOT_HANDLER_LATENCY, BOT_UPDATES_TOTAL

log = get_logger(__name__)


def _classify_event(event: TelegramObject) -> str:
    if isinstance(event, Message):
        return "message"
    if isinstance(event, CallbackQuery):
        return "callback_query"
    if isinstance(event, InlineQuery):
        return "inline_query"
    if isinstance(event, ChatMemberUpdated):
        return "chat_member"
    return "other"


def _handler_label(data: dict[str, Any]) -> str:
    """Имя хендлера (qualified) — для low-cardinality label."""
    handler = data.get("handler")
    if handler is None:
        return "unknown"
    callback = getattr(handler, "callback", None) or handler
    module = getattr(callback, "__module__", "?")
    name = getattr(callback, "__qualname__", getattr(callback, "__name__", "?"))
    return f"{module}.{name}"


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update: Update | None = data.get("event_update")
        update_id = update.update_id if update else None
        from_user = getattr(event, "from_user", None)
        chat = getattr(event, "chat", None)

        event_type = _classify_event(event)
        BOT_UPDATES_TOTAL.labels(type=event_type).inc()

        ctx_vars = structlog.contextvars.bind_contextvars(
            update_id=update_id,
            user_id=from_user.id if from_user else None,
            chat_id=chat.id if chat else None,
        )
        start = time.monotonic()
        result_label = "ok"
        try:
            return await handler(event, data)
        except Exception as exc:
            result_label = "error"
            BOT_HANDLER_ERRORS.labels(
                handler=_handler_label(data),
                error_type=type(exc).__name__,
            ).inc()
            log.exception("handler_unhandled_error")
            raise
        finally:
            elapsed = time.monotonic() - start
            BOT_HANDLER_LATENCY.labels(
                handler=_handler_label(data),
                result=result_label,
            ).observe(elapsed)
            log.info(
                "handler_finished",
                latency_ms=int(elapsed * 1000),
                event_type=type(event).__name__,
                result=result_label,
            )
            structlog.contextvars.reset_contextvars(**ctx_vars)
