"""Клавиатуры админской вкладки «Заявки на фандом»."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.application.reference.ports import FandomProposalRow
from app.presentation.bot.callback_data.admin import (
    AdminCD,
    FandomProposalAdminCD,
)
from app.presentation.bot.fandom_categories import CATEGORIES, get_category


def _short(text: str, limit: int = 36) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def build_proposals_list_kb(rows: list[FandomProposalRow]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if not rows:
        b.button(
            text="Нет открытых заявок",
            callback_data=AdminCD(action="proposals").pack(),
        )
    else:
        for r in rows:
            label = f"#{int(r.id)} · {_short(r.name)}"
            b.button(
                text=label,
                callback_data=FandomProposalAdminCD(action="open", pid=int(r.id)).pack(),
            )
    b.button(text="◀︎ Админ-меню", callback_data=AdminCD(action="root").pack())
    b.adjust(1)
    return b.as_markup()


def build_proposal_card_kb(pid: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text="✅ Одобрить",
        callback_data=FandomProposalAdminCD(action="approve_pick", pid=pid).pack(),
    )
    b.button(
        text="❌ Отклонить",
        callback_data=FandomProposalAdminCD(action="reject", pid=pid).pack(),
    )
    b.button(text="⟵ К списку", callback_data=AdminCD(action="proposals").pack())
    b.adjust(2, 1)
    return b.as_markup()


def build_proposal_approve_category_kb(*, pid: int, current_cat: str) -> InlineKeyboardMarkup:
    """Picker категорий перед approve. Текущая категория помечена ✅.

    Один клик по категории создаёт фандом сразу — отдельного шага «подтверждение»
    нет, чтобы не плодить попап-диалоги.
    """
    current = get_category(current_cat).code
    b = InlineKeyboardBuilder()
    for cat in CATEGORIES:
        prefix = "✅ " if cat.code == current else ""
        b.button(
            text=f"{prefix}{cat.short_label}",
            callback_data=FandomProposalAdminCD(action="approve_do", pid=pid, cat=cat.code).pack(),
        )
    b.button(
        text="⟵ Отмена",
        callback_data=FandomProposalAdminCD(action="open", pid=pid).pack(),
    )
    # 11 категорий по 2 в ряд + последняя одна (Other) + 1 «Отмена».
    b.adjust(2, 2, 2, 2, 2, 1, 1)
    return b.as_markup()
