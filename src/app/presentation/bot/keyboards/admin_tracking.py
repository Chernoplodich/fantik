"""Клавиатуры для управления трекинг-кодами."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.presentation.bot.callback_data.admin import AdminCD, TrackingCD


def build_tracking_menu_kb(
    items: list[tuple[int, str, str, bool]],
) -> InlineKeyboardMarkup:
    """items: list[(code_id, code, name, active)]."""
    b = InlineKeyboardBuilder()
    for code_id, code, name, active in items:
        mark = "🟢" if active else "⚫"
        b.button(
            text=f"{mark} {code} — {name[:30]}",
            callback_data=TrackingCD(action="open", code_id=code_id).pack(),
        )
    b.button(text="➕ Новый код", callback_data=TrackingCD(action="new").pack())
    b.button(text="◀︎ Админ-меню", callback_data=AdminCD(action="root").pack())
    b.adjust(1)
    return b.as_markup()


def build_tracking_card_kb(code_id: int, *, active: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text="📊 Воронка (график)",
        callback_data=TrackingCD(action="funnel", code_id=code_id).pack(),
    )
    b.button(
        text="📥 Выгрузить ID (.txt)",
        callback_data=TrackingCD(action="export_users", code_id=code_id).pack(),
    )
    if active:
        b.button(
            text="🔒 Деактивировать",
            callback_data=TrackingCD(action="deactivate", code_id=code_id).pack(),
        )
    b.button(text="◀︎ К списку", callback_data=TrackingCD(action="list").pack())
    b.adjust(1)
    return b.as_markup()


def build_tracking_funnel_back_kb(code_id: int) -> InlineKeyboardMarkup:
    """Под PNG-воронкой: назад к карточке кода + к списку + админ-меню."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀︎ К ссылке",
                    callback_data=TrackingCD(action="open", code_id=code_id).pack(),
                ),
                InlineKeyboardButton(
                    text="🔗 Все ссылки",
                    callback_data=TrackingCD(action="list").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Админ-меню",
                    callback_data=AdminCD(action="root").pack(),
                )
            ],
        ]
    )
