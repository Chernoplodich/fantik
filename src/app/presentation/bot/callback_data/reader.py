"""Callback data для читалки. Префикс `rn` для экономии байтов callback_data."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class ReadNav(CallbackData, prefix="rn"):
    """Навигация читалки.

    a — action:
        open      — открыть карточку фика (sendPhoto / sendMessage)
        read      — перейти к чтению (удалить cover, отправить первую страницу)
        prev      — предыдущая страница
        next      — следующая страница
        chapter   — переход на страницу 1 главы c
        toc       — показать оглавление
        bookmark  — toggle bookmark
        like      — toggle like
        report    — жалоба (stub до Этапа 5)
        complete  — отметить «дочитано»
        page      — переход на конкретную страницу (для TOC)
    f — fic_id
    c — chapter_no (не chapter_id! — короче)
    p — page_no
    """

    a: str
    f: int
    c: int = 0
    p: int = 0
