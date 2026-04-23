"""UI-утилиты для бесшовной админской навигации.

Цель: редактировать текущее inline-сообщение вместо отправки новых.
Когда контекст — photo (дашборд-график), удаляем фото и присылаем новое
сообщение, чтобы не копить полотенце в чате.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
)


async def render(
    event: CallbackQuery | Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> Message | None:
    """Показать текст:
    - если CallbackQuery с обычным текстовым сообщением → edit_text;
    - если сообщение с media (photo/video/...) → delete + send_message;
    - если Message (прямой ввод команды) → message.answer.
    """
    if isinstance(event, CallbackQuery):
        msg = event.message
        if msg is None:
            return None
        chat_id = msg.chat.id
        bot = event.bot
        has_media = bool(
            getattr(msg, "photo", None)
            or getattr(msg, "video", None)
            or getattr(msg, "document", None)
            or getattr(msg, "animation", None)
        )
        if has_media:
            try:
                await msg.delete()
            except TelegramBadRequest:
                pass
            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
        try:
            return await msg.edit_text(
                text=text, reply_markup=reply_markup, parse_mode=parse_mode
            )
        except TelegramBadRequest as e:
            if "not modified" in str(e):
                return None
            # Fallback: старое сообщение слишком старое/битое — шлём новое.
            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
    # Прямое сообщение (команда/ввод текста).
    return await event.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)


async def render_photo(
    event: CallbackQuery | Message,
    photo: BufferedInputFile,
    *,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = "HTML",
) -> Message | None:
    """Прислать фото:
    - для CallbackQuery: удалить предыдущее меню-сообщение и отправить photo;
    - для Message: answer_photo.

    Caption по умолчанию идёт как HTML (удобнее для <b>, <code>).
    """
    # Telegram caption: до 1024 символов. Обрежем с пометкой.
    if len(caption) > 1024:
        caption = caption[:1010] + "…\n[обрезано]"
    if isinstance(event, CallbackQuery):
        msg = event.message
        if msg is None:
            return None
        chat_id = msg.chat.id
        bot: Bot = event.bot
        try:
            await msg.delete()
        except TelegramBadRequest:
            pass
        return await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    return await event.answer_photo(
        photo=photo,
        caption=caption,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
    )


def delta_human_msk(delta_seconds: float) -> str:
    """'5ч 12мин' / '47мин' / 'через минуту'."""
    seconds = int(delta_seconds)
    if seconds < 60:
        return "менее минуты"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}мин"
    hours = minutes // 60
    minutes = minutes % 60
    if hours < 24:
        return f"{hours}ч {minutes}мин" if minutes else f"{hours}ч"
    days = hours // 24
    hours = hours % 24
    return f"{days}д {hours}ч" if hours else f"{days}д"


# Пытаемся не импортировать этот модуль в лишних местах — только где нужно.
__all__ = ["render", "render_photo", "delta_human_msk"]
