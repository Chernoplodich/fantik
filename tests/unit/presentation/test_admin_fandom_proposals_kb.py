"""Тесты клавиатуры picker'а категорий для approve fandom proposal.

Картинка происходящего: админ кликает «✅ Одобрить» в карточке заявки;
вместо немедленного approve показывается picker категорий, в котором текущая
категория (proposal.category_hint) помечена ✅. Любой клик по категории
вызывает `approve_do` с этой категорией — фандом создаётся в выбранной.
"""

from __future__ import annotations

from app.presentation.bot.callback_data.admin import FandomProposalAdminCD
from app.presentation.bot.fandom_categories import CATEGORIES
from app.presentation.bot.keyboards.admin_fandom_proposals import (
    build_proposal_approve_category_kb,
    build_proposal_card_kb,
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


class TestProposalCardKb:
    def test_approve_button_routes_to_approve_pick(self) -> None:
        """Регрессия: «Одобрить» теперь ведёт в picker, а не сразу одобряет."""
        kb = build_proposal_card_kb(pid=42)
        callbacks = _callbacks(kb)
        approve_pick = next((c for c in callbacks if "approve_pick" in c), None)
        assert approve_pick is not None
        cd = FandomProposalAdminCD.unpack(approve_pick)
        assert cd.action == "approve_pick"
        assert cd.pid == 42
        # Старого «approve» без выбора категории больше быть не должно.
        assert not any(c == "fdp:approve:42:" for c in callbacks)


class TestApproveCategoryPicker:
    def test_renders_all_11_categories(self) -> None:
        kb = build_proposal_approve_category_kb(pid=7, current_cat="anime")
        texts = _flatten(kb)
        for cat in CATEGORIES:
            assert any(cat.short_label in t for t in texts)

    def test_current_category_marked_with_checkmark(self) -> None:
        kb = build_proposal_approve_category_kb(pid=7, current_cat="series")
        texts = _flatten(kb)
        # Среди кнопок категорий ровно одна с ✅.
        marked = [t for t in texts if t.startswith("✅ ")]
        assert len(marked) == 1
        assert "Сериалы" in marked[0]

    def test_legacy_movies_maps_to_films_marker(self) -> None:
        """Категория `movies` (legacy) должна отметить кнопку «Фильмы»."""
        kb = build_proposal_approve_category_kb(pid=7, current_cat="movies")
        texts = _flatten(kb)
        marked = [t for t in texts if t.startswith("✅ ")]
        assert len(marked) == 1
        assert "Фильмы" in marked[0]

    def test_clicks_route_to_approve_do_with_category(self) -> None:
        kb = build_proposal_approve_category_kb(pid=99, current_cat="anime")
        callbacks = _callbacks(kb)
        do_cbs = [c for c in callbacks if "approve_do" in c]
        assert len(do_cbs) == len(CATEGORIES)
        # Каждый callback парсится в FandomProposalAdminCD с pid=99 и непустой cat.
        for cb_data in do_cbs:
            cd = FandomProposalAdminCD.unpack(cb_data)
            assert cd.action == "approve_do"
            assert cd.pid == 99
            assert cd.cat  # любая из 11 категорий

    def test_cancel_returns_to_open(self) -> None:
        kb = build_proposal_approve_category_kb(pid=99, current_cat="anime")
        callbacks = _callbacks(kb)
        cancel = next((c for c in callbacks if "open" in c and ":99" in c), None)
        assert cancel is not None
