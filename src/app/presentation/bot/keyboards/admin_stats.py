"""Клавиатура меню дашбордов статистики."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.presentation.bot.callback_data.admin import AdminCD, StatsCD


def build_stats_overview_kb() -> InlineKeyboardMarkup:
    """Кнопки под главным PNG-экраном статистики: дашборды + админ-меню."""
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Обновить", callback_data=StatsCD(dashboard="overview").pack())
    b.button(text="📈 Трекинг-события", callback_data=StatsCD(dashboard="tracking").pack())
    b.button(text="✍️ Топ авторов", callback_data=StatsCD(dashboard="authors").pack())
    b.button(text="📚 Топ фандомов", callback_data=StatsCD(dashboard="fandoms").pack())
    b.button(text="🛡️ Модераторы", callback_data=StatsCD(dashboard="moderators").pack())
    b.button(text="🔁 Retention", callback_data=StatsCD(dashboard="cohort").pack())
    b.button(
        text="📥 Выгрузить всех ID (.txt)",
        callback_data=StatsCD(dashboard="export_users").pack(),
    )
    b.button(text="⚙️ Админ-меню", callback_data=AdminCD(action="root").pack())
    b.adjust(1)
    return b.as_markup()


def build_stats_back_kb() -> InlineKeyboardMarkup:
    """Под вторичными дашбордами: назад к главной статистике + админ-меню."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀︎ Статистика",
                    callback_data=AdminCD(action="stats").pack(),
                ),
                InlineKeyboardButton(
                    text="⚙️ Админ-меню",
                    callback_data=AdminCD(action="root").pack(),
                ),
            ],
        ]
    )
