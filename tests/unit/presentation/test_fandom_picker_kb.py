"""Тесты общего пикера фандомов: рендер категорий + страниц + результатов поиска.

Параметр `flow` определяет набор callback'ов и поведение:
- `"create"` — single-select, есть кнопка «➕ Предложить свой».
- `"search"` — multi-select с чекбоксами, есть кнопка «✅ Готово».
- `"browse"` — single-select без propose: pick → открыть ленту фандома.
"""

from __future__ import annotations

from app.application.fanfics.ports import FandomRef
from app.domain.shared.types import FandomId
from app.presentation.bot.fandom_categories import CATEGORIES
from app.presentation.bot.keyboards.fandom_picker import (
    build_categories_kb,
    build_fandoms_in_category_kb,
    build_propose_categories_kb,
    build_search_results_kb,
)


def _flatten(kb: object) -> list[str]:
    out: list[str] = []
    for row in kb.inline_keyboard:  # type: ignore[attr-defined]
        for btn in row:
            out.append(btn.text)
    return out


def _ref(fid: int, name: str, category: str = "anime") -> FandomRef:
    return FandomRef(id=FandomId(fid), slug=f"f-{fid}", name=name, category=category)


class TestCategoriesKb:
    def test_create_mode_shows_propose_button(self) -> None:
        kb = build_categories_kb(flow="create", show_propose=True)
        texts = _flatten(kb)
        assert any("Предложить свой" in t for t in texts)
        # Все 11 категорий присутствуют.
        for cat in CATEGORIES:
            assert cat.short_label in texts

    def test_search_mode_hides_propose_and_shows_done(self) -> None:
        kb = build_categories_kb(flow="search", selected_count=2, show_propose=False)
        texts = _flatten(kb)
        assert not any("Предложить свой" in t for t in texts)
        assert any("Готово (выбрано: 2)" in t for t in texts)

    def test_browse_mode_hides_propose_and_done(self) -> None:
        """Browse — без предложения и без «Готово»: pick фандома сразу открывает ленту."""
        kb = build_categories_kb(flow="browse", show_propose=False)
        texts = _flatten(kb)
        assert not any("Предложить свой" in t for t in texts)
        assert not any("Готово" in t for t in texts)
        # Категории на месте.
        for cat in CATEGORIES:
            assert cat.short_label in texts


class TestFandomsInCategoryKb:
    def test_create_mode_renders_clean_names(self) -> None:
        fandoms = [_ref(1, "AAA"), _ref(2, "BBB")]
        kb = build_fandoms_in_category_kb(
            flow="create",
            cat="anime",
            fandoms=fandoms,
            page=0,
            has_more=False,
        )
        texts = _flatten(kb)
        assert "AAA" in texts
        assert "BBB" in texts
        # Single-mode — без чекбоксов.
        assert not any(t.startswith("✅ ") for t in texts)

    def test_search_mode_marks_selected(self) -> None:
        fandoms = [_ref(1, "AAA"), _ref(2, "BBB"), _ref(3, "CCC")]
        kb = build_fandoms_in_category_kb(
            flow="search",
            cat="anime",
            fandoms=fandoms,
            page=0,
            has_more=True,
            selected_ids={2},
        )
        texts = _flatten(kb)
        assert "✅ BBB" in texts
        assert "⬜ AAA" in texts
        assert any("Готово" in t for t in texts)

    def test_browse_mode_no_checkboxes_no_done(self) -> None:
        fandoms = [_ref(1, "Naruto"), _ref(2, "Bleach")]
        kb = build_fandoms_in_category_kb(
            flow="browse",
            cat="anime",
            fandoms=fandoms,
            page=0,
            has_more=False,
        )
        texts = _flatten(kb)
        assert "Naruto" in texts
        assert "Bleach" in texts
        assert not any(t.startswith("✅ ") or t.startswith("⬜ ") for t in texts)
        assert not any("Готово" in t for t in texts)


class TestSearchResultsKb:
    def test_renders_results_in_browse_mode(self) -> None:
        fandoms = [_ref(1, "Гарри Поттер"), _ref(2, "Гарри Дюбуа")]
        kb = build_search_results_kb(flow="browse", fandoms=fandoms)
        texts = _flatten(kb)
        assert "Гарри Поттер" in texts
        assert "Гарри Дюбуа" in texts
        assert any("К категориям" in t for t in texts)
        # Browse — без «Готово».
        assert not any("Готово" in t for t in texts)

    def test_empty_results_kb_still_navigable(self) -> None:
        kb = build_search_results_kb(flow="search", fandoms=[], selected_ids=set())
        texts = _flatten(kb)
        assert any("К категориям" in t for t in texts)
        assert any("Готово" in t for t in texts)


class TestProposeCategories:
    def test_propose_kb_contains_all_11_categories_plus_cancel(self) -> None:
        kb = build_propose_categories_kb()
        texts = _flatten(kb)
        for cat in CATEGORIES:
            assert cat.short_label in texts
        assert "Отмена" in texts
