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

from app.application.fanfics.ports import AgeRatingRef
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


def _q_label(query: str | None) -> str:
    """Компактный лейбл кнопки запроса: «✏️ Запрос: (—)» или «✏️ магия…»."""
    q = (query or "").strip()
    if not q:
        return "✏️ Запрос: (—)"
    short = q if len(q) <= 22 else (q[:21] + "…")
    return f"✏️ {short}"


def filters_root_kb(
    *,
    fandom_label: str,
    age_label: str,
    tag_label: str,
    sort: str,
    query: str | None = None,
) -> InlineKeyboardMarkup:
    """Расширенный поиск: компактный экран без длинного текста-инструкции.

    Лейблы фильтров приходят готовыми из роутера в человеческом виде —
    «🎭 Гарри Поттер» вместо «🎭 Фандом (1)», «🔞 R» вместо «🔞 Возраст (1)»,
    «🎭 Любой фандом» вместо «🎭 Фандом (0)» и т.п.
    """
    b = InlineKeyboardBuilder()
    b.row(
        _btn(_q_label(query), SearchCD(a="enter_q").pack()),
        _btn(fandom_label, SearchCD(a="pick_fandom").pack()),
    )
    b.row(
        _btn(age_label, SearchCD(a="pick_age").pack()),
        _btn(tag_label, SearchCD(a="pick_tag").pack()),
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


def query_input_kb_advanced() -> InlineKeyboardMarkup:
    """Под клавиатурой ввода q в расширенном поиске — очистить или вернуться к фильтрам.

    Используется только в advanced-flow, где запрос — часть набора сохранённых
    фильтров и его имеет смысл «Очистить», не выходя из меню.
    """
    b = InlineKeyboardBuilder()
    b.row(
        _btn("🧹 Очистить", SearchCD(a="clear_q").pack()),
        _btn("⟵ К фильтрам", SearchCD(a="filters_root").pack()),
    )
    return b.as_markup()


def query_input_kb_quick() -> InlineKeyboardMarkup:
    """Под клавиатурой быстрого поиска — только выход в каталог.

    Quick-search — разовое действие, никаких «сохранённых» данных нет,
    поэтому кнопки «Очистить» здесь не нужно (юзер просто нажмёт «Каталог»
    или введёт другое слово).
    """
    b = InlineKeyboardBuilder()
    b.row(_btn("⟵ Каталог", BrowseCD(a="root").pack()))
    return b.as_markup()


def results_kb(
    *,
    hits: list[tuple[int, str]],
    page: int,
    has_more: bool,
    degraded: bool = False,
    suggested_fandoms: list[tuple[int, str]] | None = None,
    back_target: str = "filters",
) -> InlineKeyboardMarkup:
    """Клавиатура результатов: карточки + пагинация.

    При `degraded` — пагинация и фильтры отключены (оставляем только ряд с кнопками фиков).
    `suggested_fandoms` — fallback при пустом результате: «📂 Открыть фандом …»,
    каждая ведёт в `BrowseCD(a="fandom", fd=id)`.
    `back_target`:
    - `"filters"` (по умолчанию) — нижняя строка содержит «⟵ К фильтрам»
      и «⟵ Каталог». Для поиска из расширенного режима.
    - `"catalog"` — только «⟵ Каталог». Для quick-search с корня каталога,
      где юзер не был в фильтрах и кнопка «К фильтрам» сбила бы с толку.
    """
    from app.presentation.bot.callback_data.browse import BrowseCD

    b = InlineKeyboardBuilder()
    for fic_id, title in hits:
        # Обрезаем до ~60 символов, чтобы кнопка не переполнялась.
        label = f"📖 {title[:56]}"
        b.row(_btn(label, ReadNav(a="open", f=fic_id).pack()))
    # Подсказки фандомов — показываем под результатами (или вместо них при 0 хитов).
    for fid, name in suggested_fandoms or []:
        label = f"📂 Открыть фандом «{name[:40]}»"
        b.row(_btn(label, BrowseCD(a="fandom", fd=fid, pg=0).pack()))
    if not degraded and hits:
        prev_btn = (
            _btn("◀", SearchCD(a="page", pg=page - 1).pack()) if page > 0 else _btn(" ", _NOOP)
        )
        page_btn = _btn(f"стр. {page + 1}", _NOOP)
        next_btn = (
            _btn("▶", SearchCD(a="page", pg=page + 1).pack()) if has_more else _btn(" ", _NOOP)
        )
        b.row(prev_btn, page_btn, next_btn)
    if back_target == "catalog":
        b.row(_btn("⟵ Каталог", BrowseCD(a="root").pack()))
    else:
        b.row(
            _btn("⟵ К фильтрам", SearchCD(a="filters_root").pack()),
            _btn("⟵ Каталог", BrowseCD(a="root").pack()),
        )
    return b.as_markup()
