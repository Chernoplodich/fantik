"""Клавиатуры управления фандомами."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.presentation.bot.callback_data.admin import AdminCD, FandomAdminCD


def build_fandoms_list_kb(
    items: list[tuple[int, str, bool]],
) -> InlineKeyboardMarkup:
    """items: list[(fandom_id, name, active)]."""
    b = InlineKeyboardBuilder()
    for fid, name, active in items[:30]:
        mark = "🟢" if active else "⚫"
        b.button(
            text=f"{mark} {name[:40]}",
            callback_data=FandomAdminCD(action="open", fandom_id=fid).pack(),
        )
    b.button(text="➕ Новый фандом", callback_data=FandomAdminCD(action="new").pack())
    b.button(text="◀︎ Админ-меню", callback_data=AdminCD(action="root").pack())
    b.adjust(1)
    return b.as_markup()


def build_fandom_card_kb(fandom_id: int, *, active: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    toggle_text = "⚫ Деактивировать" if active else "🟢 Активировать"
    b.button(
        text=toggle_text,
        callback_data=FandomAdminCD(action="toggle_active", fandom_id=fandom_id).pack(),
    )
    b.button(text="◀︎ К списку", callback_data=FandomAdminCD(action="list").pack())
    b.adjust(1)
    return b.as_markup()
