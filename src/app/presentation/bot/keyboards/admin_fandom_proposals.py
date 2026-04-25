"""Клавиатуры админской вкладки «Заявки на фандом»."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.application.reference.ports import FandomProposalRow
from app.presentation.bot.callback_data.admin import (
    AdminCD,
    FandomProposalAdminCD,
)


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
        callback_data=FandomProposalAdminCD(action="approve", pid=pid).pack(),
    )
    b.button(
        text="❌ Отклонить",
        callback_data=FandomProposalAdminCD(action="reject", pid=pid).pack(),
    )
    b.button(text="⟵ К списку", callback_data=AdminCD(action="proposals").pack())
    b.adjust(2, 1)
    return b.as_markup()
