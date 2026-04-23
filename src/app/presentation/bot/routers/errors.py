"""Глобальный error-handler: логирует исключения и даёт пользователю вежливое сообщение."""

from __future__ import annotations

from aiogram import Router
from aiogram.types import ErrorEvent

from app.core.errors import DomainError
from app.core.logging import get_logger
from app.presentation.bot.texts.ru import t

log = get_logger(__name__)
router = Router(name="errors")


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    exc = event.exception
    update = event.update
    log.exception(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        update_id=getattr(update, "update_id", None),
    )
    # попытка сказать пользователю "что-то пошло не так"
    try:
        if update.message is not None:
            if isinstance(exc, DomainError):
                await update.message.answer(str(exc) or t("error_generic"))
            else:
                await update.message.answer(t("error_generic"))
        elif update.callback_query is not None:
            await update.callback_query.answer(
                str(exc) if isinstance(exc, DomainError) and str(exc) else t("error_generic"),
                show_alert=True,
            )
    except Exception:
        log.warning("failed_to_notify_user_about_error")
    return True  # помечаем обработанным
