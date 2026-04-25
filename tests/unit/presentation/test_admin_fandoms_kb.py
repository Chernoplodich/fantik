"""Тесты клавиатур админ-панели фандомов.

Покрывают:
- корневой picker категорий (11 категорий + счётчики + спец-кнопки);
- список фандомов внутри категории + пагинацию;
- результаты поиска (с/без скоупа категории);
- карточку фандома (toggle/rename/aliases);
- picker категорий при создании.
"""

from __future__ import annotations

from app.application.reference.ports import FandomAdminRow
from app.domain.shared.types import FandomId
from app.presentation.bot.callback_data.admin_fandoms import FdAdmCD
from app.presentation.bot.fandom_categories import CATEGORIES
from app.presentation.bot.keyboards.admin_fandoms import (
    build_admin_create_categories_kb,
    build_admin_fandom_card_kb,
    build_admin_fandom_categories_kb,
    build_admin_fandoms_in_category_kb,
    build_admin_search_results_kb,
)


def _flatten(kb: object) -> list[str]:
    out: list[str] = []
    for row in kb.inline_keyboard:  # type: ignore[attr-defined]
        for btn in row:
            out.append(btn.text)
    return out


def _callbacks(kb: object) -> list[str]:
    out: list[str] = []
    for row in kb.inline_keyboard:  # type: ignore[attr-defined]
        for btn in row:
            out.append(btn.callback_data or "")
    return out


def _row_sizes(kb: object) -> list[int]:
    return [len(row) for row in kb.inline_keyboard]  # type: ignore[attr-defined]


def _row(fid: int, name: str, category: str = "anime", active: bool = True) -> FandomAdminRow:
    return FandomAdminRow(
        id=FandomId(fid),
        slug=f"f-{fid}",
        name=name,
        category=category,
        aliases=[],
        active=active,
    )


class TestCategoriesRoot:
    def test_renders_all_11_categories_with_counts(self) -> None:
        counts = {c.code: 5 for c in CATEGORIES}
        kb = build_admin_fandom_categories_kb(counts)
        texts = _flatten(kb)
        for cat in CATEGORIES:
            # Текст содержит short_label и счётчик.
            assert any(cat.short_label in t and "(5)" in t for t in texts)

    def test_renders_zero_for_missing_categories(self) -> None:
        kb = build_admin_fandom_categories_kb({})
        texts = _flatten(kb)
        # Для всех 11 категорий счётчик 0.
        zero_count = sum(1 for t in texts if "(0)" in t)
        assert zero_count == len(CATEGORIES)

    def test_has_search_create_back_buttons(self) -> None:
        texts = _flatten(build_admin_fandom_categories_kb({}))
        assert any("Найти" in t for t in texts)
        assert any("Новый фандом" in t for t in texts)
        assert any("Админ-меню" in t for t in texts)

    def test_layout_is_5_pairs_one_other_3_specials(self) -> None:
        sizes = _row_sizes(build_admin_fandom_categories_kb({}))
        # 5 пар (10 категорий) + 1 одиночная (Other) + 3 спец-кнопки + 1 «Назад».
        assert sizes == [2, 2, 2, 2, 2, 1, 1, 1, 1]


class TestFandomsInCategory:
    def test_renders_status_marks_and_pagination(self) -> None:
        items = [_row(1, "AAA", active=True), _row(2, "BBB", active=False)]
        kb = build_admin_fandoms_in_category_kb(cat="anime", items=items, page=0, has_more=True)
        texts = _flatten(kb)
        assert any("🟢" in t and "AAA" in t for t in texts)
        assert any("⚫" in t and "BBB" in t for t in texts)
        # Пагинация.
        assert "стр. 1" in " ".join(texts)
        assert "▶" in texts

    def test_prev_button_hidden_on_first_page(self) -> None:
        items = [_row(1, "X")]
        kb = build_admin_fandoms_in_category_kb(cat="anime", items=items, page=0, has_more=False)
        # На первой странице prev = пробел (placeholder).
        # Найдём строку пагинации (3 элемента: prev, counter, next).
        pagination = [r for r in kb.inline_keyboard if len(r) == 3][0]  # type: ignore[attr-defined]
        assert pagination[0].text == " "

    def test_create_in_category_button_present(self) -> None:
        kb = build_admin_fandoms_in_category_kb(cat="anime", items=[], page=0, has_more=False)
        callbacks = _callbacks(kb)
        new_in_cb = next(c for c in callbacks if c.startswith("fa:new_in:anime"))
        # Парсится FdAdmCD.
        cd = FdAdmCD.unpack(new_in_cb)
        assert cd.a == "new_in"
        assert cd.cat == "anime"

    def test_back_to_categories_present(self) -> None:
        kb = build_admin_fandoms_in_category_kb(cat="anime", items=[], page=0, has_more=False)
        texts = _flatten(kb)
        assert any("К категориям" in t for t in texts)


class TestSearchResults:
    def test_results_show_status_and_category(self) -> None:
        items = [_row(1, "Naruto", category="anime")]
        kb = build_admin_search_results_kb(items=items, cat="")
        texts = _flatten(kb)
        # Текст кнопки фандома содержит и название, и метку категории.
        assert any("Naruto" in t and "Аниме" in t for t in texts)

    def test_back_to_category_shown_when_scope_set(self) -> None:
        kb = build_admin_search_results_kb(items=[], cat="anime")
        texts = _flatten(kb)
        assert any("К категории" in t for t in texts)

    def test_back_to_category_hidden_when_global(self) -> None:
        kb = build_admin_search_results_kb(items=[], cat="")
        texts = _flatten(kb)
        assert not any("К категории" in t and "К категориям" not in t for t in texts)


class TestFandomCard:
    def test_active_card_offers_deactivation(self) -> None:
        kb = build_admin_fandom_card_kb(fid=42, cat="anime", active=True)
        texts = _flatten(kb)
        assert any("Деактивировать" in t for t in texts)

    def test_inactive_card_offers_activation(self) -> None:
        kb = build_admin_fandom_card_kb(fid=42, cat="anime", active=False)
        texts = _flatten(kb)
        assert any("Активировать" in t for t in texts)

    def test_card_has_rename_and_aliases_buttons(self) -> None:
        kb = build_admin_fandom_card_kb(fid=42, cat="anime", active=True)
        texts = _flatten(kb)
        assert any("Переименовать" in t for t in texts)
        assert any("Aliases" in t for t in texts)

    def test_card_layout_is_1_2_1(self) -> None:
        sizes = _row_sizes(build_admin_fandom_card_kb(fid=42, cat="anime", active=True))
        assert sizes == [1, 2, 1]


class TestCreateCategoriesPicker:
    def test_all_11_categories_present_with_cancel(self) -> None:
        kb = build_admin_create_categories_kb()
        texts = _flatten(kb)
        for cat in CATEGORIES:
            assert cat.short_label in texts
        assert any("Отмена" in t for t in texts)

    def test_callbacks_route_to_new_in(self) -> None:
        kb = build_admin_create_categories_kb()
        # Кнопка категории = FdAdmCD(a="new_in", cat=...).
        callbacks = _callbacks(kb)
        new_in_cbs = [c for c in callbacks if c.startswith("fa:new_in:")]
        assert len(new_in_cbs) == len(CATEGORIES)
