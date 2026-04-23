"""Клавиатуры поискового флоу: мультиселект фильтров + сортировка + действия.

Соглашения:
- ✅/⬜ в начале лейбла обозначает состояние чекбокса.
- callback_data сжат: используем короткие поля из `SearchCD`.
- Когда fallback активен (degraded) — фильтры недоступны: используем отдельный
  `degraded_kb` без чекбоксов.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.application.fanfics.ports import AgeRatingRef, FandomRef
from app.presentation.bot.callback_data.browse import BrowseCD
from app.presentation.bot.callback_data.reader import ReadNav
from app.presentation.bot.callback_data.search import SearchCD


_NOOP = "noop"

SORT_LABELS: dict[str, str] = {
    "relevance": "По релевантности",
    "newest": "Новые",
    "updated": "Обновлено",
    "top": "Топ по лайкам",
    "longest": "Самые длинные",
}


def _btn(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def filters_root_kb(
    *,
    fandoms_selected: int,
    ages_selected: int,
    tags_selected: int,
    sort: str,
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        _btn(
            f"🎭 Фандом ({fandoms_selected})",
            SearchCD(a="pick_fandom").pack(),
        )
    )
    b.row(
        _btn(
            f"🔞 Возраст ({ages_selected})",
            SearchCD(a="pick_age").pack(),
        )
    )
    b.row(
        _btn(
            f"🏷 Теги ({tags_selected})",
            SearchCD(a="pick_tag").pack(),
        )
    )
    b.row(
        _btn(
            f"⇅ {SORT_LABELS.get(sort, sort)}",
            SearchCD(a="pick_sort").pack(),
        )
    )
    b.row(
        _btn("🔎 Показать", SearchCD(a="apply").pack()),
        _btn("♻️ Сбросить", SearchCD(a="reset").pack()),
    )
    b.row(_btn("⟵ Каталог", BrowseCD(a="root").pack()))
    return b.as_markup()


def fandom_picker_kb(
    *,
    fandoms: list[FandomRef],
    selected_ids: set[int],
    page: int,
    has_more: bool,
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for f in fandoms:
        mark = "✅" if int(f.id) in selected_ids else "⬜"
        # pg в callback_data: чтобы после toggle перерисовать ту же страницу.
        b.row(
            _btn(
                f"{mark} {f.name}",
                SearchCD(a="toggle", k="fandom", v=str(int(f.id)), pg=page).pack(),
            )
        )
    prev_btn = (
        _btn("◀", SearchCD(a="pick_fandom", pg=page - 1).pack()) if page > 0 else _btn(" ", _NOOP)
    )
    page_btn = _btn(f"стр. {page + 1}", _NOOP)
    next_btn = (
        _btn("▶", SearchCD(a="pick_fandom", pg=page + 1).pack()) if has_more else _btn(" ", _NOOP)
    )
    b.row(prev_btn, page_btn, next_btn)
    b.row(
        _btn("✅ Готово", SearchCD(a="filters_root").pack()),
    )
    return b.as_markup()


def age_rating_picker_kb(
    *,
    items: list[AgeRatingRef],
    selected_codes: set[str],
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for it in items:
        mark = "✅" if str(it.code) in selected_codes else "⬜"
        b.row(
            _btn(
                f"{mark} {it.code} — {it.name}",
                SearchCD(a="toggle", k="age", v=str(it.code)).pack(),
            )
        )
    b.row(_btn("✅ Готово", SearchCD(a="filters_root").pack()))
    return b.as_markup()


def tag_picker_kb(
    *,
    tag_names: list[str],
    selected: set[str],
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for t in tag_names:
        mark = "✅" if t in selected else "⬜"
        # Имя тега — в callback_data. Длина имени ≤ 32 (value_object TagName),
        # prefix 's' + поля дают запас ≤ 64 байт.
        b.row(
            _btn(
                f"{mark} {t}",
                SearchCD(a="toggle", k="tag", v=t).pack(),
            )
        )
    b.row(_btn("✅ Готово", SearchCD(a="filters_root").pack()))
    return b.as_markup()


def sort_picker_kb(current: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for code, label in SORT_LABELS.items():
        mark = "✅" if code == current else "⬜"
        b.row(
            _btn(
                f"{mark} {label}",
                SearchCD(a="set_sort", v=code).pack(),
            )
        )
    b.row(_btn("⟵ К фильтрам", SearchCD(a="filters_root").pack()))
    return b.as_markup()


def results_kb(
    *,
    hits: list[tuple[int, str]],
    page: int,
    has_more: bool,
    degraded: bool = False,
) -> InlineKeyboardMarkup:
    """Клавиатура результатов: карточки + пагинация.

    При `degraded` — пагинация и фильтры отключены (оставляем только ряд с кнопками фиков).
    """
    b = InlineKeyboardBuilder()
    for fic_id, title in hits:
        # Обрезаем до ~60 символов, чтобы кнопка не переполнялась.
        label = f"📖 {title[:56]}"
        b.row(_btn(label, ReadNav(a="open", f=fic_id).pack()))
    if not degraded:
        prev_btn = (
            _btn("◀", SearchCD(a="page", pg=page - 1).pack()) if page > 0 else _btn(" ", _NOOP)
        )
        page_btn = _btn(f"стр. {page + 1}", _NOOP)
        next_btn = (
            _btn("▶", SearchCD(a="page", pg=page + 1).pack()) if has_more else _btn(" ", _NOOP)
        )
        b.row(prev_btn, page_btn, next_btn)
    b.row(
        _btn("⟵ К фильтрам", SearchCD(a="filters_root").pack()),
        _btn("⟵ Каталог", BrowseCD(a="root").pack()),
    )
    return b.as_markup()
