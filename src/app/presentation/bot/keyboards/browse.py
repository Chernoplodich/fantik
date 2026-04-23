"""Клавиатуры каталога."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.application.fanfics.ports import FandomRef
from app.presentation.bot.callback_data.browse import BrowseCD

_NOOP = "noop"


def _btn(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def browse_root_kb() -> InlineKeyboardMarkup:
    # Локальный импорт: избегаем циклов при инициализации модулей keyboards/*.
    from app.presentation.bot.callback_data.search import SearchCD

    b = InlineKeyboardBuilder()
    b.row(
        _btn("🆕 Новое", BrowseCD(a="new").pack()),
        _btn("🔥 Топ", BrowseCD(a="top").pack()),
    )
    b.row(_btn("🏷 По фэндому", BrowseCD(a="by_fandom").pack()))
    b.row(_btn("🔎 Фильтры", SearchCD(a="filters_root").pack()))
    b.row(_btn("← Главное меню", "menu:back"))
    return b.as_markup()


def fandom_pick_kb(*, fandoms: list[FandomRef], page: int, has_more: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for f in fandoms:
        b.row(
            _btn(
                f.name,
                BrowseCD(a="fandom", fd=int(f.id), pg=0).pack(),
            )
        )
    prev_btn = (
        _btn("◀", BrowseCD(a="fd_page", pg=page - 1).pack()) if page > 0 else _btn(" ", _NOOP)
    )
    page_btn = _btn(f"стр. {page + 1}", _NOOP)
    next_btn = (
        _btn("▶", BrowseCD(a="fd_page", pg=page + 1).pack()) if has_more else _btn(" ", _NOOP)
    )
    b.row(prev_btn, page_btn, next_btn)
    b.row(_btn("⟵ Каталог", BrowseCD(a="root").pack()))
    return b.as_markup()
