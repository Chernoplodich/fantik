"""Browse-flow пикера фандомов: callback'и через BrowseCD, pick → лента фандома.

Проверяет, что в browse-режиме:
- Категории генерируют callback `BrowseCD(a="fcat", v=cat_code, pg=0)`.
- «Найти по названию» → `BrowseCD(a="fsearch")`.
- «К категориям» → `BrowseCD(a="fcats")`.
- Pick фандома → `BrowseCD(a="fandom", fd=id, pg=0)` (открывает ленту, не чекбокс).
"""

from __future__ import annotations

from app.application.fanfics.ports import FandomRef
from app.domain.shared.types import FandomId
from app.presentation.bot.callback_data.browse import BrowseCD
from app.presentation.bot.fandom_categories import CATEGORIES
from app.presentation.bot.keyboards.fandom_picker import (
    build_categories_kb,
    build_fandoms_in_category_kb,
    build_search_results_kb,
)


def _all_callbacks(kb: object) -> list[str]:
    out: list[str] = []
    for row in kb.inline_keyboard:  # type: ignore[attr-defined]
        for btn in row:
            out.append(btn.callback_data or "")
    return out


def _ref(fid: int, name: str) -> FandomRef:
    return FandomRef(id=FandomId(fid), slug=f"f-{fid}", name=name, category="anime")


class TestBrowseCallbacks:
    def test_categories_use_browse_fcat_action(self) -> None:
        kb = build_categories_kb(flow="browse")
        cbs = _all_callbacks(kb)
        # Каждая категория = BrowseCD(a="fcat", v=<code>, pg=0).
        first_cat = CATEGORIES[0]
        expected = BrowseCD(a="fcat", v=first_cat.code, pg=0).pack()
        assert expected in cbs

    def test_search_button_uses_browse_fsearch(self) -> None:
        kb = build_categories_kb(flow="browse")
        cbs = _all_callbacks(kb)
        assert BrowseCD(a="fsearch").pack() in cbs

    def test_back_to_categories_uses_browse_fcats(self) -> None:
        kb = build_fandoms_in_category_kb(
            flow="browse", cat="anime", fandoms=[_ref(1, "X")], page=0, has_more=False
        )
        cbs = _all_callbacks(kb)
        assert BrowseCD(a="fcats").pack() in cbs

    def test_pick_in_browse_opens_fandom_feed(self) -> None:
        """Главное отличие browse от create/search: pick должен вести в ленту,
        а не быть мультиселектом или возвратом в форму создания."""
        fandoms = [_ref(7, "Naruto"), _ref(8, "Bleach")]
        kb = build_fandoms_in_category_kb(
            flow="browse",
            cat="anime",
            fandoms=fandoms,
            page=0,
            has_more=False,
        )
        cbs = _all_callbacks(kb)
        assert BrowseCD(a="fandom", fd=7, pg=0).pack() in cbs
        assert BrowseCD(a="fandom", fd=8, pg=0).pack() in cbs

    def test_pagination_in_browse_uses_fcat(self) -> None:
        kb = build_fandoms_in_category_kb(
            flow="browse",
            cat="games",
            fandoms=[_ref(1, "X")],
            page=2,
            has_more=True,
        )
        cbs = _all_callbacks(kb)
        # Назад: page-1=1, вперёд: page+1=3.
        assert BrowseCD(a="fcat", v="games", pg=1).pack() in cbs
        assert BrowseCD(a="fcat", v="games", pg=3).pack() in cbs

    def test_search_results_pick_in_browse_opens_feed(self) -> None:
        kb = build_search_results_kb(flow="browse", fandoms=[_ref(42, "Witcher")])
        cbs = _all_callbacks(kb)
        assert BrowseCD(a="fandom", fd=42, pg=0).pack() in cbs
