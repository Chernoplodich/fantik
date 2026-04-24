"""Фабрика экземпляра aiogram Bot."""

from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from app.core.config import Settings
from app.infrastructure.telegram.metrics_session import build_metrics_session


def build_bot(settings: Settings) -> Bot:
    """Единая точка создания Bot.

    ВАЖНО: `parse_mode` намеренно НЕ задаём по умолчанию. Мы работаем через `entities`,
    а смешивание parse_mode + entities приводит к ошибкам Telegram API. Хендлеры, которым
    нужен HTML/Markdown — выставляют parse_mode локально.

    Сессия — MetricsAiohttpSession: экспонирует `bot_tg_api_calls_total` и
    `bot_tg_api_duration_seconds`. Если задан `tg_api_base` — работает через него
    (используется load-тестами с fake-tg сервером).
    """
    session = build_metrics_session(tg_api_base=settings.tg_api_base or None)
    return Bot(
        token=settings.bot_token.get_secret_value(),
        session=session,
        default=DefaultBotProperties(
            # None = без parse_mode; форматирование только через entities
            parse_mode=None,
            protect_content=False,
            link_preview_is_disabled=True,
        ),
    )


def public_bot_username(bot: Bot) -> str | None:
    """После me.id получения username — использовать в deep-link генерации."""
    # заполняется при старте через bot.get_me()
    return None
