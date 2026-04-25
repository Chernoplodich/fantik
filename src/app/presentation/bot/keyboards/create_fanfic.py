"""Inline-клавиатуры для мастера создания фика.

Пикер фандомов вынесен в `keyboards/fandom_picker.py` (двухступенчатый
с категориями + поиском + предложением нового). Здесь остались только
вспомогательные клавиатуры мастера: возрастной рейтинг, обложка,
chapter-or-submit и универсальный «Отмена».
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.application.fanfics.ports import AgeRatingRef
from app.presentation.bot.callback_data.fanfic import (
    AgeRatingCD,
    FanficCD,
)


def build_age_rating_kb(ratings: list[AgeRatingRef]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for r in ratings:
        b.button(
            text=f"{r.code} — {r.name}",
            callback_data=AgeRatingCD(rating_id=int(r.id)),
        )
    b.adjust(1)
    return b.as_markup()


def build_cover_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Пропустить обложку", callback_data="fic_create:skip_cover")
    b.button(text="Отмена", callback_data="fic_create:cancel")
    b.adjust(1)
    return b.as_markup()


def build_chapter_or_submit_kb(fic_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(
        text="➕ Добавить главу",
        callback_data=FanficCD(action="add_chapter", fic_id=fic_id).pack(),
    )
    b.button(
        text="📤 Отправить на модерацию",
        callback_data=FanficCD(action="submit", fic_id=fic_id).pack(),
    )
    b.button(
        text="← В мои работы",
        callback_data="menu:my_works",
    )
    b.adjust(1)
    return b.as_markup()


def build_cancel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Отмена", callback_data="fic_create:cancel")
    return b.as_markup()
