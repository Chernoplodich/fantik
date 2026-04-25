"""Клавиатуры управления фандомами (админ-панель).

Двухступенчатая навигация:
1. Корень — список 11 категорий с счётчиками + поиск + создание + назад.
2. Внутри категории — пагинированный список фандомов + поиск + создание в категории + к категориям.
3. Поиск — отдельный экран с результатами.
4. Карточка — toggle/rename/aliases + к списку.

Все callback'и идут через `FdAdmCD` (короткие поля под лимит 64 байта).
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.application.reference.ports import FandomAdminRow
from app.presentation.bot.callback_data.admin import AdminCD
from app.presentation.bot.callback_data.admin_fandoms import FdAdmCD
from app.presentation.bot.fandom_categories import CATEGORIES, category_short_label

PAGE_SIZE: int = 10
_NOOP = "noop"


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


# ============================================================
# Шаг 1: список категорий
# ============================================================


def build_admin_fandom_categories_kb(counts: dict[str, int]) -> InlineKeyboardMarkup:
    """Корень админ-фандомов: 11 категорий + спец-кнопки.

    counts — `{category_code: active_count}`. Категории без активных получают 0.
    """
    b = InlineKeyboardBuilder()
    for cat in CATEGORIES:
        n = int(counts.get(cat.code, 0))
        b.button(
            text=f"{cat.short_label} ({n})",
            callback_data=FdAdmCD(a="cat", cat=cat.code, pg=0).pack(),
        )
    b.button(text="🔍 Найти по названию", callback_data=FdAdmCD(a="search").pack())
    b.button(text="➕ Новый фандом", callback_data=FdAdmCD(a="new").pack())
    b.button(text="◀︎ Админ-меню", callback_data=AdminCD(action="root").pack())
    # 5 пар категорий + 1 одиночная (Other) + 3 спец-кнопки.
    b.adjust(2, 2, 2, 2, 2, 1, 1, 1, 1)
    return b.as_markup()


# ============================================================
# Шаг 2: фандомы внутри категории
# ============================================================


def build_admin_fandoms_in_category_kb(
    *,
    cat: str,
    items: list[FandomAdminRow],
    page: int,
    has_more: bool,
) -> InlineKeyboardMarkup:
    """Список фандомов внутри категории + пагинация + спец-кнопки."""
    b = InlineKeyboardBuilder()
    for f in items:
        mark = "🟢" if f.active else "⚫"
        b.row(
            _btn(
                f"{mark} {f.name[:38]}",
                FdAdmCD(a="open", cat=cat, fid=int(f.id)).pack(),
            )
        )
    # Ряд пагинации: ◀ / стр. N / ▶.
    prev_btn = (
        _btn("◀", FdAdmCD(a="cat", cat=cat, pg=page - 1).pack()) if page > 0 else _btn(" ", _NOOP)
    )
    page_btn = _btn(f"стр. {page + 1}", _NOOP)
    next_btn = (
        _btn("▶", FdAdmCD(a="cat", cat=cat, pg=page + 1).pack()) if has_more else _btn(" ", _NOOP)
    )
    b.row(prev_btn, page_btn, next_btn)
    # Спец-кнопки: поиск (с категорией) + создание в категории.
    cat_short = category_short_label(cat)
    b.row(
        _btn("🔍 Найти", FdAdmCD(a="search", cat=cat).pack()),
        _btn(f"➕ В «{cat_short[:14]}»", FdAdmCD(a="new_in", cat=cat).pack()),
    )
    b.row(_btn("⟵ К категориям", FdAdmCD(a="root").pack()))
    return b.as_markup()


# ============================================================
# Шаг 3: результаты поиска
# ============================================================


def build_admin_search_results_kb(
    *,
    items: list[FandomAdminRow],
    cat: str = "",
) -> InlineKeyboardMarkup:
    """Результаты поиска + повторный поиск + к категориям.

    Если `cat` непуст — поиск шёл внутри категории и кнопка возврата ведёт в неё.
    """
    b = InlineKeyboardBuilder()
    for f in items:
        mark = "🟢" if f.active else "⚫"
        b.row(
            _btn(
                f"{mark} {f.name[:38]} · {category_short_label(f.category)}",
                FdAdmCD(a="open", cat=f.category, fid=int(f.id)).pack(),
            )
        )
    b.row(_btn("🔍 Искать ещё", FdAdmCD(a="search", cat=cat).pack()))
    if cat:
        b.row(_btn("⟵ К категории", FdAdmCD(a="cat", cat=cat, pg=0).pack()))
    b.row(_btn("⟵ К категориям", FdAdmCD(a="root").pack()))
    return b.as_markup()


# ============================================================
# Карточка фандома: toggle / rename / aliases / back
# ============================================================


def build_admin_fandom_card_kb(*, fid: int, cat: str, active: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    toggle_text = "⚫ Деактивировать" if active else "🟢 Активировать"
    b.button(
        text=toggle_text,
        callback_data=FdAdmCD(a="toggle", cat=cat, fid=fid).pack(),
    )
    b.button(
        text="✏️ Переименовать",
        callback_data=FdAdmCD(a="rename", cat=cat, fid=fid).pack(),
    )
    b.button(
        text="✏️ Aliases",
        callback_data=FdAdmCD(a="aliases", cat=cat, fid=fid).pack(),
    )
    b.button(
        text="⟵ К списку",
        callback_data=FdAdmCD(a="cat", cat=cat, pg=0).pack(),
    )
    b.adjust(1, 2, 1)
    return b.as_markup()


# ============================================================
# Picker категорий при создании нового фандома (без preset)
# ============================================================


def build_admin_create_categories_kb() -> InlineKeyboardMarkup:
    """Шаг 1 FSM создания: выбрать категорию.

    Каждая кнопка ведёт в `new_in` с preset категорией → шаг 2 (название).
    """
    b = InlineKeyboardBuilder()
    for cat in CATEGORIES:
        b.button(
            text=cat.short_label,
            callback_data=FdAdmCD(a="new_in", cat=cat.code).pack(),
        )
    b.button(text="⟵ Отмена", callback_data=FdAdmCD(a="root").pack())
    # 11 кнопок по 2 в ряд + последняя одна (Отмена).
    b.adjust(2, 2, 2, 2, 2, 1, 1)
    return b.as_markup()


# ============================================================
# Кнопка возврата из FSM-сообщений (универсальная)
# ============================================================


def build_admin_fandoms_back_kb(*, cat: str = "") -> InlineKeyboardMarkup:
    """Минимальная клавиатура с одной кнопкой назад.

    Используется в подсказках FSM (например, после прерывания ввода).
    """
    target = FdAdmCD(a="cat", cat=cat, pg=0).pack() if cat else FdAdmCD(a="root").pack()
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⟵ К списку", callback_data=target)]]
    )
