"""Клавиатуры для модерационной панели."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.domain.moderation.value_objects import RejectionReason
from app.presentation.bot.callback_data.moderation import ModCD, ReasonCD

_NOOP = "noop"


def _btn(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def build_mod_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎯 Следующая работа", callback_data=ModCD(action="pick").pack())
    b.button(text="← Главное меню", callback_data="menu:back")
    b.adjust(1)
    return b.as_markup()


def build_mod_card_kb(*, case_id: int, chapter_ids: list[tuple[int, int]]) -> InlineKeyboardMarkup:
    """chapter_ids: [(chapter_id, number), ...]"""
    b = InlineKeyboardBuilder()
    for ch_id, num in chapter_ids:
        b.button(
            text=f"📖 Глава {num}",
            callback_data=ModCD(action="read_chapter", case_id=case_id, chapter_id=ch_id).pack(),
        )
    b.button(
        text="✅ Одобрить",
        callback_data=ModCD(action="approve", case_id=case_id).pack(),
    )
    b.button(
        text="❌ Отклонить",
        callback_data=ModCD(action="reject", case_id=case_id).pack(),
    )
    b.button(text="🎯 Следующая", callback_data=ModCD(action="pick").pack())
    b.adjust(2, 1, 1, 1)
    return b.as_markup()


def build_reason_picker_kb(
    *, case_id: int, reasons: list[RejectionReason], selected: set[int]
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for r in reasons:
        mark = "☑️" if int(r.id) in selected else "⬜"
        b.button(
            text=f"{mark} {r.title}",
            callback_data=ReasonCD(action="toggle", case_id=case_id, reason_id=int(r.id)).pack(),
        )
    b.button(
        text="Далее →",
        callback_data=ReasonCD(action="confirm", case_id=case_id).pack(),
    )
    b.button(
        text="Отмена",
        callback_data=ModCD(action="menu").pack(),
    )
    b.adjust(1)
    return b.as_markup()


def build_reject_preview_kb(case_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text="Подтвердить отказ",
        callback_data=ModCD(action="reject_confirm", case_id=case_id).pack(),
    )
    b.button(text="Отмена", callback_data=ModCD(action="menu").pack())
    b.adjust(1)
    return b.as_markup()


def build_mod_page_kb(
    *,
    case_id: int,
    chapter_id: int,
    chapter_no: int,
    page_no: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Клавиатура страницы главы в режиме модерации.

    Три ряда:
      ◀ Назад | N/M | Дальше ▶
      [← К карточке]
      [✅ Одобрить] [❌ Отклонить]

    Это — ОДНО сообщение с edit_text-навигацией, как у читателя.
    Без спама в ЛС даже на 10-страничных главах.
    """
    b = InlineKeyboardBuilder()

    # Ряд 1: навигация по страницам.
    prev_btn = (
        _btn(
            "◀ Назад",
            ModCD(
                action="mod_page",
                case_id=case_id,
                chapter_id=chapter_id,
                page_no=page_no - 1,
            ).pack(),
        )
        if page_no > 1
        else _btn(" ", _NOOP)
    )
    counter = _btn(f"📄 гл.{chapter_no} · {page_no}/{total_pages}", _NOOP)
    next_btn = (
        _btn(
            "Дальше ▶",
            ModCD(
                action="mod_page",
                case_id=case_id,
                chapter_id=chapter_id,
                page_no=page_no + 1,
            ).pack(),
        )
        if page_no < total_pages
        else _btn(" ", _NOOP)
    )
    b.row(prev_btn, counter, next_btn)

    # Ряд 2: возврат к карточке.
    b.row(
        _btn(
            "← К карточке",
            ModCD(action="back_to_card", case_id=case_id).pack(),
        )
    )

    # Ряд 3: решения (дают одобрить/отклонить прямо из чтения).
    b.row(
        _btn("✅ Одобрить", ModCD(action="approve", case_id=case_id).pack()),
        _btn("❌ Отклонить", ModCD(action="reject", case_id=case_id).pack()),
    )
    return b.as_markup()
