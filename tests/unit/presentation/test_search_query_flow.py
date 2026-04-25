"""FSM-flow свободного запроса (q): сохранение, передача в SearchUseCase, очистка.

После UX-итерации `on_query_text` обёрнут `@inject` и принимает reference + search_uc:
- если флаг `_q_quick=True` — сразу запускает search_uc и показывает результаты;
- иначе — возвращает в filters_root с подтверждающим сообщением.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.application.fanfics.ports import FandomRef
from app.application.search.dto import SearchCommand, SearchHit, SearchResult
from app.domain.shared.types import FandomId, FanficId
from app.presentation.bot.callback_data.search import SearchCD
from app.presentation.bot.routers import browse as br

from ._flow_helpers import make_callback, make_message, make_state, unwrap

apply_filters = unwrap(br.apply_filters)
on_query_text = unwrap(br.on_query_text)


class _FakeRef:
    async def get_fandom(self, _: FandomId) -> FandomRef | None:
        return None

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


def _empty_search_uc() -> AsyncMock:
    async def _impl(_: SearchCommand) -> SearchResult:
        return SearchResult(hits=[], total=0, degraded=False, facets={})

    return AsyncMock(side_effect=_impl)


@pytest.mark.asyncio
async def test_query_text_saved_to_fsm_in_normal_mode() -> None:
    """Расширенный поиск: после ввода q возвращаемся в filters_root."""
    state = make_state()
    msg = make_message(text="магия и приключения")
    await on_query_text(msg, state, _FakeRef(), _empty_search_uc())
    data = await state.get_data()
    assert data["s_q"] == "магия и приключения"


@pytest.mark.asyncio
async def test_too_short_query_is_rejected() -> None:
    state = make_state()
    msg = make_message(text="а")
    await on_query_text(msg, state, _FakeRef(), _empty_search_uc())
    data = await state.get_data()
    # Слишком короткий — не сохраняем.
    assert "s_q" not in data or data["s_q"] in ("", None)


@pytest.mark.asyncio
async def test_quick_mode_runs_search_immediately() -> None:
    """Если юзер пришёл через QuickQCD (`_qk_active=True`), после ввода q
    SearchUseCase вызывается сразу с qk_q, без захода в filters_root."""
    state = make_state()
    await state.update_data(_qk_active=True, qk_q="", qk_fandoms=[])
    msg = make_message(text="магия")
    captured: dict[str, SearchCommand] = {}

    async def _search_uc(cmd: SearchCommand) -> SearchResult:
        captured["cmd"] = cmd
        return SearchResult(hits=[], total=0, degraded=False, facets={})

    await on_query_text(msg, state, _FakeRef(), AsyncMock(side_effect=_search_uc))

    assert captured.get("cmd") is not None
    assert captured["cmd"].q == "магия"
    # quick остаётся активным (для пагинации); s_q не затронут:
    data = await state.get_data()
    assert data.get("_qk_active") is True
    assert data.get("qk_q") == "магия"
    assert data.get("s_q") in (None, "")


@pytest.mark.asyncio
async def test_normal_mode_does_not_run_search() -> None:
    state = make_state()
    msg = make_message(text="магия")
    search_uc = _empty_search_uc()
    await on_query_text(msg, state, _FakeRef(), search_uc)
    search_uc.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_filters_passes_q_to_use_case() -> None:
    state = make_state()
    await state.update_data(s_q="магия", s_fandoms=[1], s_ages=[], s_tags=[], s_sort="relevance")
    cb = make_callback()

    captured: dict[str, SearchCommand] = {}

    async def _search_uc(cmd: SearchCommand) -> SearchResult:
        captured["cmd"] = cmd
        return SearchResult(hits=[], total=0, degraded=False, facets={})

    search_uc = AsyncMock(side_effect=_search_uc)
    await apply_filters(cb, SearchCD(a="apply", pg=0), state, search_uc, _FakeRef())

    assert captured["cmd"].q == "магия"
    assert captured["cmd"].fandoms == [1]


@pytest.mark.asyncio
async def test_apply_filters_with_empty_q_works_too() -> None:
    state = make_state()
    await state.update_data(s_q="", s_fandoms=[], s_ages=[], s_tags=[], s_sort="newest")
    cb = make_callback()
    captured: dict[str, SearchCommand] = {}

    async def _search_uc(cmd: SearchCommand) -> SearchResult:
        captured["cmd"] = cmd
        return SearchResult(
            hits=[
                SearchHit(
                    fic_id=FanficId(1),
                    title="t",
                    author_nick=None,
                    fandom_id=FandomId(1),
                    fandom_name=None,
                    age_rating="G",
                    likes_count=0,
                    chapters_count=1,
                )
            ],
            total=1,
            degraded=False,
            facets={},
        )

    search_uc = AsyncMock(side_effect=_search_uc)
    await apply_filters(cb, SearchCD(a="apply", pg=0), state, search_uc, _FakeRef())
    assert captured["cmd"].q == ""


@pytest.mark.asyncio
async def test_quick_search_with_no_hits_suggests_matching_fandom() -> None:
    """Регрессия: юзер пишет «наруто», 0 фиков — но в каталоге есть фандом «Наруто».
    Бот должен предложить «📂 Открыть фандом «Наруто»» кнопкой."""
    state = make_state()
    await state.update_data(_qk_active=True, qk_q="", qk_fandoms=[])
    msg = make_message(text="наруто")

    class _RefWithFandom:
        async def get_fandom(self, _: FandomId) -> FandomRef | None:
            return None

        async def list_fandoms_paginated(self, **_: Any) -> tuple[list[FandomRef], int]:
            return [], 0

        async def list_fandoms_by_category(self, **_: Any) -> tuple[list[FandomRef], int]:
            return [], 0

        async def search_fandoms(self, **_: Any) -> list[FandomRef]:
            return [
                FandomRef(
                    id=FandomId(99), slug="naruto", name="Наруто", category="anime"
                )
            ]

        async def list_age_ratings(self) -> list[Any]:
            return []

        async def get_age_rating(self, _: int) -> Any:
            return None

    search_uc = AsyncMock(
        side_effect=lambda _cmd: SearchResult(hits=[], total=0, degraded=False, facets={})
    )

    await on_query_text(msg, state, _RefWithFandom(), search_uc)

    # Проверяем, что в reply_markup есть кнопка с открытием фандома Наруто.
    msg.answer.assert_awaited()
    sent_kb = msg.answer.call_args.kwargs.get("reply_markup")
    assert sent_kb is not None
    btn_texts = [
        btn.text for row in sent_kb.inline_keyboard for btn in row
    ]
    assert any("Открыть фандом" in t and "Наруто" in t for t in btn_texts)
