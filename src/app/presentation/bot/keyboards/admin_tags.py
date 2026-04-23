"""Клавиатуры merge-тегов."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.presentation.bot.callback_data.admin import AdminCD, TagAdminCD


def build_tag_candidates_kb(
    candidates: list[tuple[int, str, int, str]],
) -> InlineKeyboardMarkup:
    """candidates: list[(canonical_id, canonical_name, source_id, source_name)]."""
    b = InlineKeyboardBuilder()
    for canonical_id, canonical_name, source_id, source_name in candidates[:20]:
        label = f"«{source_name}» → «{canonical_name}»"
        b.button(
            text=label[:60],
            callback_data=TagAdminCD(
                action="merge",
                canonical_id=canonical_id,
                source_id=source_id,
            ).pack(),
        )
    b.button(text="◀︎ Админ-меню", callback_data=AdminCD(action="root").pack())
    b.adjust(1)
    return b.as_markup()
