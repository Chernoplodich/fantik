"""Общий двухступенчатый пикер фандомов: категории → фандомы внутри категории.

Один пикер используется тремя сценариями (`flow`):

* `"create"` — мастер создания/правки фика. Single-select. callback'и через
  `FandomPickCD`. Включает «➕ Предложить свой» (для `EditFanficStates` пикер
  передаёт `show_propose=False`).
* `"search"` — фильтр расширенного поиска. Multi-select с чекбоксами. callback'и
  через `SearchCD`. «Готово» возвращает в `filters_root`.
* `"browse"` — просмотр каталога «🎭 По фэндому» (single-select без шага submit:
  выбор фандома сразу открывает ленту). callback'и через `BrowseCD`.

Чтобы не плодить три копии клавиатур, callback'и собираются callback-фабриками
ниже, разводимыми по `flow`.
"""

from __future__ import annotations

from typing import Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.application.fanfics.ports import FandomRef
from app.presentation.bot.callback_data.browse import BrowseCD
from app.presentation.bot.callback_data.fanfic import FandomPickCD
from app.presentation.bot.callback_data.search import SearchCD
from app.presentation.bot.fandom_categories import (
    CATEGORIES,
    category_long_label,
)

PickerFlow = Literal["create", "search", "browse"]

FANDOMS_PER_PAGE: int = 10
_NOOP = "noop"


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _is_multi(flow: PickerFlow) -> bool:
    return flow == "search"


# ---------- callback factories: разводим create / search / browse ----------


def _cb_categories_root(flow: PickerFlow) -> str:
    if flow == "search":
        return SearchCD(a="pick_fandom").pack()
    if flow == "browse":
        return BrowseCD(a="fcats").pack()
    return FandomPickCD(action="cats").pack()


def _cb_category(flow: PickerFlow, cat: str, page: int = 0) -> str:
    if flow == "search":
        return SearchCD(a="cat", v=cat, pg=page).pack()
    if flow == "browse":
        return BrowseCD(a="fcat", v=cat, pg=page).pack()
    return FandomPickCD(action="cat", cat=cat, page=page).pack()


def _cb_search(flow: PickerFlow) -> str:
    if flow == "search":
        return SearchCD(a="fsearch").pack()
    if flow == "browse":
        return BrowseCD(a="fsearch").pack()
    return FandomPickCD(action="search").pack()


def _cb_propose(flow: PickerFlow) -> str:
    # propose работает только в create-flow; в остальных — кнопка не показывается.
    return FandomPickCD(action="propose").pack()


def _cb_pick(flow: PickerFlow, fandom_id: int, page: int = 0) -> str:
    if flow == "search":
        return SearchCD(a="toggle", k="fandom", v=str(fandom_id), pg=page).pack()
    if flow == "browse":
        # Browse: pick = открыть ленту фандома (BrowseCD a="fandom", fd=id).
        return BrowseCD(a="fandom", fd=fandom_id, pg=0).pack()
    return FandomPickCD(action="pick", fandom_id=fandom_id).pack()


def _cb_done(flow: PickerFlow) -> str:
    # «Готово» имеет смысл только в multi-режиме (search) — single-режимы
    # (create/browse) закрываются на pick.
    return SearchCD(a="filters_root").pack() if flow == "search" else _NOOP


def _exit_button(flow: PickerFlow) -> tuple[str, str] | None:
    """Кнопка выхода из пикера во внешний экран.

    Без неё пользователь застревает на корне категорий: «⟵ К категориям»
    есть только на втором уровне и в search-результатах. Возвращаем
    (label, callback_data) или None, если у этого flow нет «внешнего» экрана
    для возврата (create — выход через `Cancel` в мастере).
    """
    if flow == "browse":
        return ("⟵ Каталог", BrowseCD(a="root").pack())
    if flow == "search":
        return ("⟵ К фильтрам", SearchCD(a="filters_root").pack())
    return None


# ============================================================
# Шаг 1: список категорий
# ============================================================


def build_categories_kb(
    *,
    flow: PickerFlow,
    selected_count: int = 0,
    show_propose: bool = True,
) -> InlineKeyboardMarkup:
    multi = _is_multi(flow)
    b = InlineKeyboardBuilder()
    # Категории по 2 в ряд.
    for cat in CATEGORIES:
        b.button(text=cat.short_label, callback_data=_cb_category(flow, cat.code, 0))
    # adjust выставится в конце; сначала добавим спец-кнопки.
    spec = InlineKeyboardBuilder()
    spec.button(text="🔍 Найти по названию", callback_data=_cb_search(flow))
    if flow == "create" and show_propose:
        spec.button(text="➕ Предложить свой", callback_data=_cb_propose(flow))
    if multi:
        # «Готово» с счётчиком — позволяет вернуться к корню фильтров.
        spec.button(
            text=f"✅ Готово (выбрано: {selected_count})",
            callback_data=_cb_done(flow),
        )
    # Выход во внешний экран (caталог / расширенные фильтры). Без этой
    # кнопки на корне пикера юзер застревает.
    exit_btn = _exit_button(flow)
    if exit_btn is not None:
        spec.button(text=exit_btn[0], callback_data=exit_btn[1])
    spec.adjust(1)

    b.adjust(2)
    b.attach(spec)
    return b.as_markup()


# ============================================================
# Шаг 2: фандомы внутри категории
# ============================================================


def build_fandoms_in_category_kb(
    *,
    flow: PickerFlow,
    cat: str,
    fandoms: list[FandomRef],
    page: int,
    has_more: bool,
    selected_ids: set[int] | None = None,
) -> InlineKeyboardMarkup:
    multi = _is_multi(flow)
    selected_ids = selected_ids or set()
    b = InlineKeyboardBuilder()
    for f in fandoms:
        prefix = ""
        if multi:
            prefix = "✅ " if int(f.id) in selected_ids else "⬜ "
        b.row(_btn(f"{prefix}{f.name}", _cb_pick(flow, int(f.id), page)))
    # Пагинация.
    prev_btn = _btn("◀", _cb_category(flow, cat, page - 1)) if page > 0 else _btn(" ", _NOOP)
    page_btn = _btn(f"стр. {page + 1}", _NOOP)
    next_btn = _btn("▶", _cb_category(flow, cat, page + 1)) if has_more else _btn(" ", _NOOP)
    b.row(prev_btn, page_btn, next_btn)
    # Спец-кнопки.
    b.row(_btn("🔍 Найти по названию", _cb_search(flow)))
    b.row(_btn("⟵ К категориям", _cb_categories_root(flow)))
    if multi:
        b.row(
            _btn(
                f"✅ Готово (выбрано: {len(selected_ids)})",
                _cb_done(flow),
            )
        )
    exit_btn = _exit_button(flow)
    if exit_btn is not None:
        b.row(_btn(exit_btn[0], exit_btn[1]))
    return b.as_markup()


# ============================================================
# Шаг 3: результаты поиска по подстроке
# ============================================================


def build_search_results_kb(
    *,
    flow: PickerFlow,
    fandoms: list[FandomRef],
    selected_ids: set[int] | None = None,
) -> InlineKeyboardMarkup:
    multi = _is_multi(flow)
    selected_ids = selected_ids or set()
    b = InlineKeyboardBuilder()
    for f in fandoms:
        prefix = ""
        if multi:
            prefix = "✅ " if int(f.id) in selected_ids else "⬜ "
        b.row(_btn(f"{prefix}{f.name}", _cb_pick(flow, int(f.id))))
    b.row(_btn("🔍 Искать ещё", _cb_search(flow)))
    b.row(_btn("⟵ К категориям", _cb_categories_root(flow)))
    if multi:
        b.row(
            _btn(
                f"✅ Готово (выбрано: {len(selected_ids)})",
                _cb_done(flow),
            )
        )
    exit_btn = _exit_button(flow)
    if exit_btn is not None:
        b.row(_btn(exit_btn[0], exit_btn[1]))
    return b.as_markup()


# ============================================================
# Категории при предложении нового фандома (только create-flow)
# ============================================================


def build_propose_categories_kb() -> InlineKeyboardMarkup:
    """Выбор категории для нового предложенного фандома.

    Использует FandomProposeCategoryCD из callback_data/fanfic.py.
    """
    from app.presentation.bot.callback_data.fanfic import FandomProposeCategoryCD

    b = InlineKeyboardBuilder()
    for cat in CATEGORIES:
        b.button(
            text=cat.short_label,
            callback_data=FandomProposeCategoryCD(cat=cat.code).pack(),
        )
    b.button(text="Отмена", callback_data="fic_create:cancel")
    b.adjust(2, 2, 2, 2, 2, 2, 1)  # 11 кнопок по 2 в ряд + последняя (Отмена)
    return b.as_markup()


# ============================================================
# Заголовки для разных шагов (для use в роутерах)
# ============================================================


CATEGORIES_INTRO_TEXT = (
    "🎭 <b>Выбери фандом</b>\n\n"
    "Где искать?\n"
    "Выбери категорию или используй поиск по названию.\n\n"
    "Не нашёл свой? Нажми «➕ Предложить свой» — добавим после проверки."
)

CATEGORIES_INTRO_TEXT_SEARCH = (
    "🎭 <b>Фандом</b>\n\n"
    "Можно отметить несколько — найдём работы из любой выбранной вселенной.\n"
    "Выбери категорию или нажми «🔍 Найти по названию»."
)

SEARCH_PROMPT_TEXT = (
    "🔍 <b>Найти фандом</b>\n\n"
    "Напиши часть названия (минимум 2 символа). Можно по-русски или по-английски."
)

PROPOSE_NAME_PROMPT = (
    "➕ <b>Предложить новый фандом</b>\n\n"
    "Шаг 1/2: пришли название (как в оригинале или по-русски).\n"
    "Например: «Тёмная башня», «Hollow Knight»."
)

PROPOSE_CATEGORY_PROMPT = (
    "➕ <b>Предложить новый фандом</b>\n\nШаг 2/2: к какой категории относится?"
)


def category_screen_title(cat: str) -> str:
    long = category_long_label(cat)
    return f"<b>{long}</b>\n\nВыбери фандом или нажми «🔍 Найти по названию»."
