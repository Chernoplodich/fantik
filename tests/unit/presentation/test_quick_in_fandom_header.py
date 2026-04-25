"""Регрессии:
1. При quick-search с preset фандомом заголовок результатов содержит
   «Поиск в фандоме «<имя>»» — юзер видит, что ищет внутри фандома, а
   не во всём каталоге.
2. При quick-search в фандоме фандом-fallback (предложить «открыть фандом»)
   НЕ показывается — юзер уже в этом фандоме.
3. catalog root содержит inline-подсказку @<bot_username> когда username
   доступен.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.application.fanfics.ports import FandomRef
from app.application.search.dto import SearchResult
from app.domain.shared.types import FandomId
from app.presentation.bot.callback_data.browse import QuickQCD
from app.presentation.bot.routers import browse as br

from ._flow_helpers import make_callback, make_message, make_state, unwrap


class _FakeRef:
    def __init__(self, by_id: dict[int, FandomRef] | None = None) -> None:
        self._by_id = by_id or {}

    async def get_fandom(self, fid: FandomId) -> FandomRef | None:
        return self._by_id.get(int(fid))

    async def list_fandoms_paginated(self, **_: Any) -> tuple[list[FandomRef], int]:
        return [], 0

    async def list_fandoms_by_category(self, **_: Any) -> tuple[list[FandomRef], int]:
        return [], 0

    async def search_fandoms(self, **_: Any) -> list[FandomRef]:
        # Если бы fallback вызвался — увидели бы Гарри Поттера в подсказках.
        return [
            FandomRef(id=FandomId(99), slug="hp", name="Гарри Поттер", category="books")
        ]

    async def list_age_ratings(self) -> list[Any]:
        return []

    async def get_age_rating(self, _: int) -> Any:
        return None


@pytest.mark.asyncio
async def test_quick_in_fandom_results_have_fandom_in_header() -> None:
    """E2E: quick_query_in_fandom → ввод текста → header содержит «в фандоме «X»»."""
    state = make_state()
    cb = make_callback()
    naruto = FandomRef(id=FandomId(7), slug="naruto", name="Наруто", category="anime")
    ref = _FakeRef(by_id={7: naruto})

    quick_in_fandom = unwrap(br.quick_query_in_fandom)
    await quick_in_fandom(cb, QuickQCD(a="in_fandom", fd=7), state, ref)

    msg = make_message(text="арка")
    on_query_text = unwrap(br.on_query_text)
    search_uc = AsyncMock(
        side_effect=lambda _: SearchResult(hits=[], total=0, degraded=False, facets={})
    )
    await on_query_text(msg, state, ref, search_uc)

    msg.answer.assert_awaited()
    sent_body = msg.answer.call_args.args[0]
    assert "в фандоме «Наруто»" in sent_body


@pytest.mark.asyncio
async def test_quick_in_fandom_no_results_does_not_offer_open_fandom() -> None:
    """Регрессия: внутри фандома при пустом результате НЕ предлагать «📂 Открыть фандом»
    (юзер уже в нём). Только текст «попробуй другое слово»."""
    state = make_state()
    cb = make_callback()
    naruto = FandomRef(id=FandomId(7), slug="naruto", name="Наруто", category="anime")
    ref = _FakeRef(by_id={7: naruto})

    quick_in_fandom = unwrap(br.quick_query_in_fandom)
    await quick_in_fandom(cb, QuickQCD(a="in_fandom", fd=7), state, ref)

    msg = make_message(text="мегамозг")
    on_query_text = unwrap(br.on_query_text)
    search_uc = AsyncMock(
        side_effect=lambda _: SearchResult(hits=[], total=0, degraded=False, facets={})
    )
    await on_query_text(msg, state, ref, search_uc)

    sent_kb = msg.answer.call_args.kwargs.get("reply_markup")
    btn_texts = [btn.text for row in sent_kb.inline_keyboard for btn in row]
    # Никаких «Открыть фандом» — мы и так в фандоме.
    assert not any("Открыть фандом" in t for t in btn_texts)


def test_catalog_text_includes_inline_hint_when_username_set() -> None:
    body = br._catalog_root_text("MyTestBot")
    assert "@MyTestBot" in body
    assert "слово" in body


def test_catalog_text_omits_inline_hint_when_no_username() -> None:
    body = br._catalog_root_text(None)
    assert "@" not in body
