"""Клавиатуры «Моей полки»."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.application.reading.ports import ShelfItem
from app.presentation.bot.callback_data.reader import ReadNav
from app.presentation.bot.callback_data.shelf import ShelfCD


def _btn(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def shelf_tabs_kb(*, active: str) -> InlineKeyboardMarkup:
    """Верхний ряд табов: recent / bookmarks / likes."""
    b = InlineKeyboardBuilder()

    def _label(code: str, text: str) -> str:
        return ("• " + text) if code == active else text

    b.row(
        _btn(_label("recent", "🕒 Недавно"), ShelfCD(a="recent").pack()),
        _btn(_label("bookmarks", "📑 Закладки"), ShelfCD(a="bookmarks").pack()),
        _btn(_label("likes", "❤️ Лайки"), ShelfCD(a="likes").pack()),
    )
    return b.as_markup()


def shelf_list_kb(*, active: str, items: list[ShelfItem]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()

    def _label(code: str, text: str) -> str:
        return ("• " + text) if code == active else text

    b.row(
        _btn(_label("recent", "🕒 Недавно"), ShelfCD(a="recent").pack()),
        _btn(_label("bookmarks", "📑 Закладки"), ShelfCD(a="bookmarks").pack()),
        _btn(_label("likes", "❤️ Лайки"), ShelfCD(a="likes").pack()),
    )
    for item in items:
        title = item.title
        if item.chapter_number is not None and item.page_no is not None and item.chapter_number > 0:
            title = f"{title} · гл.{item.chapter_number} стр.{item.page_no}"
        if len(title) > 60:
            title = title[:57] + "…"
        b.row(_btn(title, ReadNav(a="open", f=int(item.fic_id)).pack()))
    b.row(_btn("← Главное меню", "menu:back"))
    return b.as_markup()
