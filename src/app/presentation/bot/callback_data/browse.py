"""Callback data для каталога."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class BrowseCD(CallbackData, prefix="br"):
    """Лента каталога + двухступенчатый пикер фандома «По фэндому».

    a — action:
        root       — корень (меню)
        new        — лента «Новое»
        top        — лента «Топ»
        by_fandom  — открыть пикер: показать категории
        fcats      — вернуться к списку категорий из поиска/категории
        fcat       — открыть фандомы внутри категории (v=код категории, pg=страница)
        fsearch    — войти во ввод подстроки для поиска фандома
        fandom     — выбрать фэндом и показать его ленту (fd=fandom_id)
        page       — пагинация внутри ленты
    fd — fandom_id (0 = без фильтра)
    pg — page offset
    v  — код категории (для action=fcat); пустая для остальных
    """

    a: str
    fd: int = 0
    pg: int = 0
    v: str = ""


class QuickQCD(CallbackData, prefix="qq"):
    """Быстрая точка входа в текстовый поиск с корневого экрана каталога.

    Делает то же, что и `SearchCD(a='enter_q')`, но после ввода текста
    сразу показывает результаты — без захода в фильтры. Помечает FSM-data
    флагом `_q_quick=True`, чтобы `on_query_text` знал, что юзер пришёл
    из быстрого режима.

    Действия:
    - `start`     — поиск с пустыми фильтрами.
    - `in_fandom` — поиск с предустановленным `s_fandoms=[fd]` (из ленты фандома).
    """

    a: str
    fd: int = 0
