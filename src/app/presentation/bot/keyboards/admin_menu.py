"""Клавиатуры админского корневого меню."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.presentation.bot.callback_data.admin import AdminCD


def build_admin_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    # Группа 1: операционные коммуникации.
    b.button(text="📣 Рассылки", callback_data=AdminCD(action="broadcasts").pack())
    b.button(text="🔗 Трекинг", callback_data=AdminCD(action="tracking").pack())
    # Группа 2: аналитика.
    b.button(text="📊 Статистика", callback_data=AdminCD(action="stats").pack())
    # Группа 3: справочники.
    b.button(text="📚 Фандомы", callback_data=AdminCD(action="fandoms").pack())
    b.button(text="📋 Заявки", callback_data=AdminCD(action="proposals").pack())
    b.button(text="🏷️ Теги (merge)", callback_data=AdminCD(action="tags").pack())
    # Возврат: callback menu:back обработан универсально в profile.py.
    b.button(text="◀︎ Главное меню", callback_data="menu:back")
    b.adjust(2, 1, 2, 1, 1)
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
