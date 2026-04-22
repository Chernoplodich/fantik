"""Callback data для каталога."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class BrowseCD(CallbackData, prefix="br"):
    """Лента каталога.

    a — action:
        root       — корень (меню)
        new        — лента «Новое»
        top        — лента «Топ»
        by_fandom  — открыть список фэндомов для фильтра
        fd_page    — страница списка фэндомов (pg=номер)
        fandom     — выбрать фэндом и показать его ленту
        page       — пагинация внутри ленты
    fd — fandom_id (0 = без фильтра)
    pg — page offset (каждая страница — 10 фиков / 12 фэндомов)
    """

    a: str
    fd: int = 0
    pg: int = 0
