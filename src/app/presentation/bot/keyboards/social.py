"""Клавиатуры для подписок и жалоб."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.application.reports.ports import ReportListItem
from app.domain.reports.value_objects import REPORT_REASON_CODES, REPORT_REASON_TITLES
from app.presentation.bot.callback_data.social import (
    RepMod,
    RepReason,
    RepStart,
    SubNav,
)


def subscribe_button(*, fic_id: int, is_subscribed: bool) -> InlineKeyboardButton:
    if is_subscribed:
        return InlineKeyboardButton(
            text="🔕 Отписаться",
            callback_data=SubNav(a="unsub", f=fic_id).pack(),
        )
    return InlineKeyboardButton(
        text="🔔 Подписаться",
        callback_data=SubNav(a="sub", f=fic_id).pack(),
    )


def report_fic_button(fic_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text="⚠️ Жалоба",
        callback_data=RepStart(t="fic", id=fic_id).pack(),
    )


def report_chapter_button(chapter_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text="⚠️ Жалоба",
        callback_data=RepStart(t="ch", id=chapter_id).pack(),
    )


def report_reason_picker_kb() -> InlineKeyboardMarkup:
    """Inline-меню выбора причины жалобы (одиночный выбор)."""
    b = InlineKeyboardBuilder()
    for code in REPORT_REASON_CODES:
        b.row(
            InlineKeyboardButton(
                text=REPORT_REASON_TITLES[code],
                callback_data=RepReason(code=code).pack(),
            )
        )
    return b.as_markup()


def mod_reports_menu_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text="⚠️ Жалобы",
        callback_data=RepMod(a="list", id=0, p=0).pack(),
    )


def reports_list_kb(
    *, items: list[ReportListItem], page: int, has_more: bool
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if not items:
        b.row(
            InlineKeyboardButton(
                text="← В меню",
                callback_data="menu:mod",
            )
        )
        return b.as_markup()

    for it in items:
        label = f"#{int(it.id)} · {it.target_type.value}#{it.target_id}"
        if it.reason_code:
            label = f"{label} · {it.reason_code}"
        b.row(
            InlineKeyboardButton(
                text=label[:60],
                callback_data=RepMod(a="card", id=int(it.id), p=page).pack(),
            )
        )
    prev_cb = RepMod(a="list", id=0, p=max(page - 1, 0)).pack() if page > 0 else "noop"
    next_cb = RepMod(a="list", id=0, p=page + 1).pack() if has_more else "noop"
    b.row(
        InlineKeyboardButton(text="◀" if page > 0 else " ", callback_data=prev_cb),
        InlineKeyboardButton(text=f"стр. {page + 1}", callback_data="noop"),
        InlineKeyboardButton(text="▶" if has_more else " ", callback_data=next_cb),
    )
    b.row(
        InlineKeyboardButton(text="← В меню", callback_data="menu:mod"),
    )
    return b.as_markup()


def report_card_kb(*, report_id: int, can_action: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="❎ Отклонить",
            callback_data=RepMod(a="dismiss", id=report_id).pack(),
        )
    )
    if can_action:
        b.row(
            InlineKeyboardButton(
                text="🗑 Архивировать фик",
                callback_data=RepMod(a="action", id=report_id).pack(),
            )
        )
    b.row(
        InlineKeyboardButton(
            text="← Список",
            callback_data=RepMod(a="list", id=0, p=0).pack(),
        )
    )
    return b.as_markup()
