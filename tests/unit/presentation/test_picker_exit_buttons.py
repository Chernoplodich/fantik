"""Регрессии: пользователь не должен застревать в пикере фандомов.

На каждом экране (категории / категория / результаты поиска) должна быть
явная кнопка выхода во внешний экран:
- browse-flow → «⟵ Каталог».
- search-flow → «⟵ К фильтрам».
- create-flow — выход через «Отмена» в FSM мастера, в самом пикере не нужен.
"""

from __future__ import annotations

from app.application.fanfics.ports import FandomRef
from app.domain.shared.types import FandomId
from app.presentation.bot.callback_data.browse import BrowseCD
from app.presentation.bot.callback_data.search import SearchCD
from app.presentation.bot.keyboards.fandom_picker import (
    build_categories_kb,
    build_fandoms_in_category_kb,
    build_search_results_kb,
)


def _flatten(kb: object) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for row in kb.inline_keyboard:  # type: ignore[attr-defined]
        for btn in row:
            out.append((btn.text, btn.callback_data or ""))
    return out


def _ref(fid: int, name: str) -> FandomRef:
    return FandomRef(id=FandomId(fid), slug=f"f-{fid}", name=name, category="anime")


# ---------- browse-flow: должен иметь «⟵ Каталог» на каждом экране ----------


class TestBrowseFlowExitButtons:
    def test_categories_root_has_catalog_exit(self) -> None:
        kb = build_categories_kb(flow="browse", show_propose=False)
        items = _flatten(kb)
        assert ("⟵ Каталог", BrowseCD(a="root").pack()) in items

    def test_fandoms_in_category_has_catalog_exit(self) -> None:
        kb = build_fandoms_in_category_kb(
            flow="browse",
            cat="anime",
            fandoms=[_ref(1, "X")],
            page=0,
            has_more=False,
        )
        items = _flatten(kb)
        assert ("⟵ Каталог", BrowseCD(a="root").pack()) in items
        # «⟵ К категориям» тоже должна остаться (это отдельный уровень).
        assert any(t == "⟵ К категориям" for t, _ in items)

    def test_search_results_have_catalog_exit(self) -> None:
        kb = build_search_results_kb(flow="browse", fandoms=[_ref(1, "X")])
        items = _flatten(kb)
        assert ("⟵ Каталог", BrowseCD(a="root").pack()) in items


# ---------- search-flow: «⟵ К фильтрам» как exit ----------


class TestSearchFlowExitButtons:
    def test_categories_root_has_filters_exit(self) -> None:
        kb = build_categories_kb(flow="search", selected_count=0, show_propose=False)
        items = _flatten(kb)
        assert ("⟵ К фильтрам", SearchCD(a="filters_root").pack()) in items

    def test_fandoms_in_category_has_filters_exit(self) -> None:
        kb = build_fandoms_in_category_kb(
            flow="search",
            cat="anime",
            fandoms=[_ref(1, "X")],
            page=0,
            has_more=False,
            selected_ids=set(),
        )
        items = _flatten(kb)
        assert ("⟵ К фильтрам", SearchCD(a="filters_root").pack()) in items


# ---------- create-flow: exit через Cancel мастера, в пикере его нет ----------


class TestCreateFlowNoExitButton:
    def test_categories_root_has_no_external_exit(self) -> None:
        kb = build_categories_kb(flow="create", show_propose=True)
        items = _flatten(kb)
        labels = [t for t, _ in items]
        # Никакого «⟵ Каталог» / «⟵ К фильтрам» — выход через FSM Cancel.
        assert not any("Каталог" in t for t in labels)
        assert not any("К фильтрам" in t for t in labels)
