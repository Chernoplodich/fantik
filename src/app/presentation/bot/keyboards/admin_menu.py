"""Клавиатуры админского корневого меню."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.presentation.bot.callback_data.admin import AdminCD


def build_admin_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📣 Рассылки", callback_data=AdminCD(action="broadcasts").pack())
    b.button(text="🔗 Трекинг", callback_data=AdminCD(action="tracking").pack())
    b.button(text="📊 Статистика", callback_data=AdminCD(action="stats").pack())
    b.button(text="📚 Фандомы", callback_data=AdminCD(action="fandoms").pack())
    b.button(text="🏷️ Теги (merge)", callback_data=AdminCD(action="tags").pack())
    b.button(text="◀︎ Назад", callback_data="menu:main")
    b.adjust(1)
    return b.as_markup()


def build_back_to_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀︎ Админ-меню",
                    callback_data=AdminCD(action="root").pack(),
                ),
            ],
        ]
    )
