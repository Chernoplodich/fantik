"""Logging middleware: биндит контекст к structlog на время обработки апдейта."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from app.core.logging import get_logger

log = get_logger(__name__)


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

        ctx_vars = structlog.contextvars.bind_contextvars(
            update_id=update_id,
            user_id=from_user.id if from_user else None,
            chat_id=chat.id if chat else None,
        )
        start = time.monotonic()
        try:
            return await handler(event, data)
        except Exception:
            log.exception("handler_unhandled_error")
            raise
        finally:
            latency_ms = int((time.monotonic() - start) * 1000)
            log.info("handler_finished", latency_ms=latency_ms, event_type=type(event).__name__)
            structlog.contextvars.reset_contextvars(**ctx_vars)
