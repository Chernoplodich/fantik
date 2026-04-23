"""Фабрика экземпляра aiogram Bot."""

from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties

from app.core.config import Settings


def build_bot(settings: Settings) -> Bot:
    """Единая точка создания Bot.

    ВАЖНО: `parse_mode` намеренно НЕ задаём по умолчанию. Мы работаем через `entities`,
    а смешивание parse_mode + entities приводит к ошибкам Telegram API. Хендлеры, которым
    нужен HTML/Markdown — выставляют parse_mode локально.
    """
    return Bot(
        token=settings.bot_token.get_secret_value(),
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
