"""Регрессии: back_target для quick-search и кнопка «🔎 Поиск в этом фандоме».

1. Quick-search (с корня каталога) → результаты должны иметь только
   кнопку «⟵ Каталог», без «⟵ К фильтрам». Юзер не был в фильтрах,
   незачем туда отправлять.
2. Расширенный поиск → результаты сохраняют обе кнопки.
3. Из ленты фандома кнопка «🔎 Поиск в этом фандоме» → quick-flow с
   preset `s_fandoms=[fid]` и подсказкой про фандом в prompt'е.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.application.fanfics.ports import FandomRef
from app.application.search.dto import SearchCommand, SearchResult
from app.domain.shared.types import FandomId
from app.presentation.bot.callback_data.browse import QuickQCD
from app.presentation.bot.callback_data.search import SearchCD
from app.presentation.bot.keyboards.search_filters import results_kb
from app.presentation.bot.routers import browse as br

from ._flow_helpers import make_callback, make_message, make_state, unwrap


def _kb_texts(kb: object) -> list[str]:
    out: list[str] = []
    for row in kb.inline_keyboard:  # type: ignore[attr-defined]
        for btn in row:
            out.append(btn.text)
    return out


# ---------- 1) results_kb back_target ----------


class TestResultsKbBackTarget:
    def test_default_target_filters_shows_both_buttons(self) -> None:
        kb = results_kb(hits=[(1, "x")], page=0, has_more=False)
        texts = _kb_texts(kb)
        assert any("К фильтрам" in t for t in texts)
        assert any("Каталог" in t for t in texts)

    def test_target_catalog_shows_only_catalog(self) -> None:
        kb = results_kb(
            hits=[(1, "x")], page=0, has_more=False, back_target="catalog"
        )
        texts = _kb_texts(kb)
        assert not any("К фильтрам" in t for t in texts)
        assert any("Каталог" in t for t in texts)


# ---------- 2) FSM-flag back_target проброс через quick-search ----------


class _FakeRef:
    def __init__(self, fandom: FandomRef | None = None) -> None:
        self._f = fandom

    async def get_fandom(self, _: FandomId) -> FandomRef | None:
        return self._f

    async def list_fandoms_paginated(self, **_: Any) -> tuple[list[FandomRef], int]:
        return [], 0

    async def list_fandoms_by_category(self, **_: Any) -> tuple[list[FandomRef], int]:
        return [], 0

    async def search_fandoms(self, **_: Any) -> list[FandomRef]:
        return []

    async def list_age_ratings(self) -> list[Any]:
        return []

    async def get_age_rating(self, _: int) -> Any:
        return None


@pytest.mark.asyncio
class TestQuickFlowIsolation:
    async def test_quick_query_start_writes_qk_namespace(self) -> None:
        state = make_state()
        cb = make_callback()
        await br.quick_query_start(cb, state)
        data = await state.get_data()
        assert data.get("_qk_active") is True
        assert data.get("qk_q") == ""
        assert data.get("qk_fandoms") == []
        # Не трогает расширенные фильтры:
        assert "s_q" not in data
        assert "s_fandoms" not in data

    async def test_quick_in_fandom_presets_qk_fandoms_only(self) -> None:
        state = make_state()
        cb = make_callback()
        ref = _FakeRef(
            FandomRef(id=FandomId(7), slug="hp", name="Гарри Поттер", category="books")
        )
        quick_in_fandom = unwrap(br.quick_query_in_fandom)
        await quick_in_fandom(cb, QuickQCD(a="in_fandom", fd=7), state, ref)
        data = await state.get_data()
        assert data.get("_qk_active") is True
        assert data.get("qk_fandoms") == [7]
        # s_fandoms (расширенный) не трогается:
        assert "s_fandoms" not in data

    async def test_enter_query_clears_qk_namespace(self) -> None:
        """При входе в расширенный поиск quick-данные должны очищаться."""
        state = make_state()
        # Имитируем «остатки» quick-сессии:
        await state.update_data(_qk_active=True, qk_q="наруто", qk_fandoms=[7])
        cb = make_callback()
        await br.enter_query(cb, state)
        data = await state.get_data()
        assert data.get("_qk_active") is False
        assert data.get("qk_q") == ""
        assert data.get("qk_fandoms") == []

    async def test_advanced_search_does_not_leak_quick_q(self) -> None:
        """Регрессия: quick «наруто» НЕ должно появиться в s_q расширенного."""
        state = make_state()
        cb = make_callback()
        await br.quick_query_start(cb, state)
        msg = make_message(text="наруто")
        on_query_text = unwrap(br.on_query_text)
        search_uc = AsyncMock(
            side_effect=lambda _: SearchResult(hits=[], total=0, degraded=False, facets={})
        )
        await on_query_text(msg, state, _FakeRef(), search_uc)
        data = await state.get_data()
        # quick сохранил у себя:
        assert data.get("qk_q") == "наруто"
        # расширенный не затронут:
        assert data.get("s_q") in (None, "")


# ---------- 3) on_query_text quick-mode → results_kb уважает back_target ----------


@pytest.mark.asyncio
async def test_quick_search_results_have_only_catalog_button() -> None:
    """E2E-связка: quick_query_start → ввод текста → результат без «К фильтрам»."""
    state = make_state()
    cb = make_callback()
    await br.quick_query_start(cb, state)
    msg = make_message(text="что-то")

    on_query_text = unwrap(br.on_query_text)
    search_uc = AsyncMock(
        side_effect=lambda _: SearchResult(hits=[], total=0, degraded=False, facets={})
    )
    await on_query_text(msg, state, _FakeRef(), search_uc)

    sent_kb = msg.answer.call_args.kwargs.get("reply_markup")
    assert sent_kb is not None
    texts = _kb_texts(sent_kb)
    assert not any("К фильтрам" in t for t in texts), (
        "quick-search не должен возвращать в расширенный поиск"
    )
    assert any("Каталог" in t for t in texts)


@pytest.mark.asyncio
async def test_advanced_filters_show_both_back_buttons() -> None:
    """Если зашёл из расширенного поиска — кнопка «К фильтрам» осталась."""
    state = make_state()
    await state.update_data(
        _back_target="filters",
        s_q="магия",
        s_fandoms=[],
        s_ages=[],
        s_tags=[],
        s_sort="relevance",
    )
    cb = make_callback()
    apply_filters = unwrap(br.apply_filters)
    search_uc = AsyncMock(
        side_effect=lambda _: SearchResult(hits=[], total=0, degraded=False, facets={})
    )
    await apply_filters(cb, SearchCD(a="apply", pg=0), state, search_uc, _FakeRef())

    # `cb` — AsyncMock, isinstance(cb, CallbackQuery) ложно, поэтому
    # `_show_search_results` уходит в message-ветку и вызывает sender.answer(...)
    # с reply_markup. В реальном рантайме это путь edit_text, но для теста
    # достаточно проверить, что в kb есть нужная кнопка.
    cb.answer.assert_awaited()
    kb = cb.answer.call_args.kwargs.get("reply_markup")
    assert kb is not None
    texts = _kb_texts(kb)
    assert any("К фильтрам" in t for t in texts)
