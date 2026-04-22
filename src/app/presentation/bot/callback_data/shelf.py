"""Callback data для «Моей полки»."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class ShelfCD(CallbackData, prefix="sh"):
    """Полка пользователя.

    a — action:
        recent    — недавно читал
        bookmarks — закладки
        likes     — лайки
        page      — пагинация
    pg — offset page
    """

    a: str
    pg: int = 0
