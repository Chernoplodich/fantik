"""Inline-клавиатуры для мастера создания фика."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.application.fanfics.ports import AgeRatingRef, FandomRef
from app.presentation.bot.callback_data.fanfic import (
    AgeRatingCD,
    FandomPickCD,
    FanficCD,
)

FANDOM_PAGE_SIZE = 10


def build_fandom_picker_kb(
    *, fandoms: list[FandomRef], page: int, total: int
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for f in fandoms:
        b.button(
            text=f.name,
            callback_data=FandomPickCD(action="pick", fandom_id=int(f.id)),
        )
    b.adjust(1)

    nav = InlineKeyboardBuilder()
    max_page = max(0, (total - 1) // FANDOM_PAGE_SIZE)
    if page > 0:
        nav.button(
            text="◀",
            callback_data=FandomPickCD(action="page", page=page - 1),
        )
    if page < max_page:
        nav.button(
            text="▶",
            callback_data=FandomPickCD(action="page", page=page + 1),
        )
    if nav.buttons:
        b.attach(nav)
        nav.adjust(2)
    return b.as_markup()


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
